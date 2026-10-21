#!/usr/bin/env python3
"""Safe, staged updates for the M-series desktop packages.

Design and trust model: mseries/UPDATER-DESIGN.md. In short:

  check     refresh the signed repository metadata and list available updates
  stage     download + verify the update set and its rollback set (installs nothing)
  apply     install the staged set now (the boot unit calls `boot` instead)
  boot      early-boot entry: recover an interrupted transaction, roll back an
            update that never reached a healthy session, apply a staged set
  confirm   after login: wait for a healthy session, then make the set known-good
  rollback  restore the package set that was installed before the last update
  status    machine- and human-readable state; log shows the update log

Nothing here restarts Wingpanel, the dock or the compositor: dpkg replaces files
by rename, so a running session keeps its old copies until the next login.
Stdlib only. Every system interaction goes through Backend or System so the
tests can replace apt, dpkg and the power/network/session probes.
"""
import argparse
import configparser
import contextlib
import datetime
import fcntl
import fnmatch
import glob
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time

SCHEMA = 1
EXIT_FAILED, EXIT_USAGE, EXIT_ROLLBACK_FAILED, EXIT_BUSY = 1, 2, 3, 75
CHANNELS = ('stable', 'dev')
DEFAULTS = {
    'channel': 'stable',
    'packages': 'mseries-* pantheon-rust-compositor',
    'auto_stage': 'false',
    'min_battery_percent': '30',
    'min_free_mb': '300',
    'max_unconfirmed_boots': '2',
    'session_processes': 'io.elementary.wingpanel',
    'confirm_timeout_seconds': '600',
}


class UpdateError(Exception):
    """An expected failure: reported on one line, nothing half-applied."""


class RollbackFailed(UpdateError):
    """The machine is not on a known-good set; needs attention."""


class Busy(UpdateError):
    pass


def utcnow():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_atomic(path, text):
    """Replace path with text so a crash leaves the old or the new file, never half."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f'.{path.name}.{os.getpid()}.tmp')
    with open(temporary, 'w') as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    fsync_directory(path.parent)


class Paths:
    """Every filesystem location, overridable for tests (MSERIES_UPDATE_*)."""

    def __init__(self, env=None):
        env = os.environ if env is None else env
        self.state = Path(env.get('MSERIES_UPDATE_STATE', '/var/lib/mseries-update'))
        self.config = Path(env.get('MSERIES_UPDATE_CONFIG', '/etc/mseries-update/mseries-update.conf'))
        self.sources_dir = Path(env.get('MSERIES_UPDATE_SOURCES', '/etc/mseries-update/sources.list.d'))
        self.log = Path(env.get('MSERIES_UPDATE_LOG', '/var/log/mseries-update.log'))
        self.power = Path(env.get('MSERIES_UPDATE_POWER', '/sys/class/power_supply'))
        self.dpkg_lock = Path(env.get('MSERIES_UPDATE_DPKG_LOCK', '/var/lib/dpkg/lock-frontend'))
        self.health_dir = Path(env.get('MSERIES_UPDATE_HEALTH_D', '/etc/mseries-update/health.d'))

    @property
    def state_file(self):
        return self.state / 'state.json'

    @property
    def sources_file(self):
        return self.sources_dir / 'mseries.sources'

    @property
    def store(self):
        return self.state / 'store'

    @property
    def staged(self):
        return self.state / 'staged'

    @property
    def pending_marker(self):
        return self.state / 'pending-confirm'

    @property
    def lock(self):
        return self.state / 'lock'


class Config:
    def __init__(self, path):
        self.path = Path(path)
        parser = configparser.ConfigParser(interpolation=None)
        parser.read_dict({'update': DEFAULTS})
        if self.path.exists():
            parser.read(self.path)
        self.values = dict(parser['update'])
        unknown = set(self.values) - set(DEFAULTS)
        if unknown:
            raise UpdateError(f'unknown setting(s) in {self.path}: {", ".join(sorted(unknown))}')
        self.validate()

    channel = property(lambda self: self.values['channel'])
    patterns = property(lambda self: self.values['packages'].split())
    auto_stage = property(lambda self: self.values['auto_stage'].lower() in ('1', 'true', 'yes', 'on'))
    min_battery = property(lambda self: int(self.values['min_battery_percent']))
    min_free_bytes = property(lambda self: int(self.values['min_free_mb']) << 20)
    max_unconfirmed_boots = property(lambda self: int(self.values['max_unconfirmed_boots']))
    session_processes = property(lambda self: self.values['session_processes'].split())
    confirm_timeout = property(lambda self: int(self.values['confirm_timeout_seconds']))

    def set(self, key, value):
        if key not in DEFAULTS:
            raise UpdateError(f'unknown setting {key!r}; known: {", ".join(DEFAULTS)}')
        previous = self.values[key]
        self.values[key] = value
        try:
            self.validate()
        except UpdateError:
            self.values[key] = previous
            raise
        parser = configparser.ConfigParser(interpolation=None)
        parser['update'] = {k: v for k, v in self.values.items() if v != DEFAULTS[k]}
        lines = ['[update]'] + [f'{k} = {v}' for k, v in parser['update'].items()]
        write_atomic(self.path, '\n'.join(lines) + '\n')

    def validate(self):
        if self.channel not in CHANNELS:
            raise UpdateError(f'channel must be one of {", ".join(CHANNELS)}, not {self.channel!r}')
        for key in ('min_battery_percent', 'min_free_mb', 'max_unconfirmed_boots', 'confirm_timeout_seconds'):
            if not self.values[key].isdigit():
                raise UpdateError(f'{key} must be a whole number')


class BackendError(UpdateError):
    pass


class Backend:
    """apt-get/dpkg behind one seam. Only the mseries repository is ever consulted:
    a private source list and private lists directory, so the updater never refreshes,
    upgrades or pins the rest of the system."""

    def __init__(self, paths, run=None, dpkg_args=(), query_args=(), apt_extra=()):
        # The *_args seams let tests drive the real apt and dpkg against a scratch root.
        self.paths = paths
        self.run = run or self._run
        self.dpkg_args, self.query_args, self.apt_extra = list(dpkg_args), list(query_args), list(apt_extra)

    def _run(self, command, cwd=None, check=True):
        environment = dict(os.environ, DEBIAN_FRONTEND='noninteractive', LC_ALL='C')
        result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True)
        if check and result.returncode != 0:
            tail = (result.stderr or result.stdout).strip().splitlines()[-6:]
            raise BackendError(f'{command[0]} failed ({result.returncode}): ' + ' | '.join(tail))
        return result

    def apt_options(self):
        lists = self.paths.state / 'apt' / 'lists'
        lists.mkdir(parents=True, exist_ok=True)
        (lists / 'partial').mkdir(exist_ok=True)
        options = self.apt_extra + [
            '-o', f'Dir::Etc::sourcelist={self.paths.sources_file}', '-o', 'Dir::Etc::sourceparts=-',
            '-o', f'Dir::State::Lists={lists}', '-o', 'APT::Get::List-Cleanup=0',
            '-o', 'Dir::Cache::pkgcache=', '-o', 'Dir::Cache::srcpkgcache=',
            '-o', 'Acquire::Languages=none',
        ]
        return options

    def refresh(self):
        if not self.paths.sources_file.exists():
            raise UpdateError(f'no update source configured ({self.paths.sources_file}); run: mseries-update init')
        self.run(['apt-get', 'update', '--error-on=any', '-qq'] + self.apt_options())

    def installed(self, patterns):
        output = self.run(['dpkg-query'] + self.query_args + ['-W', '-f', '${Package}\t${Version}\t${db:Status-Abbrev}\n']).stdout
        found = {}
        for line in output.splitlines():
            name, _, rest = line.partition('\t')
            version, _, status = rest.partition('\t')
            if status.startswith('ii') and any(fnmatch.fnmatch(name, pattern) for pattern in patterns):
                found[name] = version
        return found

    def candidates(self, names):
        """name -> candidate version offered by the mseries repository (or the installed one)."""
        if not names:
            return {}
        output = self.run(['apt-cache', 'policy'] + self.apt_options() + sorted(names)).stdout
        candidates, current = {}, None
        for line in output.splitlines():
            if re.match(r'^\S.*:$', line):
                current = line[:-1]
            elif current and line.strip().startswith('Candidate:'):
                value = line.split(':', 1)[1].strip()
                candidates[current] = None if value == '(none)' else value
        return candidates

    def download(self, specs, destination):
        """Fetch name=version and any missing dependencies into destination; install nothing.
        Plan with a simulated install, then fetch each exact version: this also works for
        a file: mirror, where `install --download-only` leaves the .debs where they are."""
        plan = self.run(['apt-get', '--simulate', 'install', '--no-install-recommends', '-y']
                        + self.apt_options() + specs).stdout
        wanted = re.findall(r'^Inst (\S+)(?: \[[^\]]+\])? \((\S+) ', plan, re.MULTILINE)
        if not wanted:
            raise BackendError('apt planned no packages to fetch for ' + ' '.join(specs))
        Path(destination).mkdir(parents=True, exist_ok=True)
        return sorted(self.download_exact(name, version, destination) for name, version in wanted)

    def download_exact(self, name, version, destination):
        Path(destination).mkdir(parents=True, exist_ok=True)
        self.run(['apt-get', 'download'] + self.apt_options() + [f'{name}={version}'], cwd=destination)
        found = self.find_deb(name, version, [destination])
        if not found:
            raise BackendError(f'{name} {version} is no longer available from the update repository')
        return found

    def find_deb(self, name, version, directories):
        encoded = version.replace(':', '%3a')
        for directory in directories:
            for candidate in sorted(Path(directory).glob(f'{name}_{encoded}_*.deb')):
                return candidate
        return None

    def deb_info(self, deb):
        output = self.run(['dpkg-deb', '-f', str(deb), 'Package', 'Version']).stdout
        fields = dict(line.split(': ', 1) for line in output.splitlines() if ': ' in line)
        return fields['Package'], fields['Version']

    def install_debs(self, debs):
        self.run(['dpkg'] + self.dpkg_args + ['-i', '--force-confold'] + [str(deb) for deb in debs])

    def remove(self, names):
        if names:
            self.run(['dpkg'] + self.dpkg_args + ['--remove'] + sorted(names))

    def compare(self, left, right):
        """-1, 0, 1 like cmp(left, right) in dpkg version order."""
        for operator, value in (('lt', -1), ('eq', 0)):
            if self.run(['dpkg', '--compare-versions', left, operator, right], check=False).returncode == 0:
                return value
        return 1

    def audit(self):
        return self.run(['dpkg'] + self.dpkg_args + ['--audit'], check=False).stdout.strip()

    def verify(self, names):
        """File-integrity problems for the given packages (empty list = healthy)."""
        problems = []
        result = self.run(['dpkg'] + self.dpkg_args + ['--verify'] + sorted(names), check=False)
        problems += [f'dpkg --verify: {line}' for line in result.stdout.splitlines() if line.strip()]
        for name in sorted(names):
            for path in self.run(['dpkg-query'] + self.query_args + ['-L', name], check=False).stdout.splitlines():
                if path.endswith('.so') and os.path.isfile(path):
                    missing = [line.strip() for line in self.run(['ldd', path], check=False).stdout.splitlines()
                               if 'not found' in line]
                    problems += [f'{name}: {path}: {line}' for line in missing]
        return problems


class System:
    """Probes of the machine outside apt: power, disk, network, locks, the desktop session."""

    def __init__(self, paths):
        self.paths = paths

    def free_bytes(self, path):
        path = Path(path)
        while not path.exists():
            path = path.parent
        usage = os.statvfs(path)
        return usage.f_bavail * usage.f_frsize

    def power(self):
        """('ac'|'battery'|'unknown', percent or None). No supplies listed = a desktop on AC."""
        online, capacity, seen = False, None, False
        for supply in sorted(glob.glob(str(self.paths.power / '*'))):
            kind = self._read(Path(supply) / 'type')
            seen = seen or bool(kind)
            if kind == 'Mains' and self._read(Path(supply) / 'online') == '1':
                online = True
            elif kind == 'Battery' and self._read(Path(supply) / 'capacity').isdigit():
                capacity = int(self._read(Path(supply) / 'capacity'))
        if online or not seen:
            return 'ac', capacity
        return ('battery' if capacity is not None else 'unknown'), capacity

    @staticmethod
    def _read(path):
        try:
            return Path(path).read_text().strip()
        except OSError:
            return ''

    def network_ok(self):
        text = self._read(self.paths.sources_file)
        hosts = set()
        for uri in re.findall(r'^URIs:\s*(\S+)', text, re.MULTILINE):
            match = re.match(r'(https?)://([^/:]+)(?::(\d+))?', uri)
            if match:
                hosts.add((match.group(2), int(match.group(3) or (443 if match.group(1) == 'https' else 80))))
            elif uri.startswith('file:'):
                return True
        if not hosts:
            return False
        for host, port in hosts:
            try:
                socket.create_connection((host, port), timeout=8).close()
            except OSError:
                return False
        return True

    def metered(self):
        if not shutil.which('nmcli'):
            return False
        result = subprocess.run(['nmcli', '-t', '-f', 'GENERAL.METERED', 'device', 'show'],
                                capture_output=True, text=True, check=False)
        return any(line.split(':', 1)[-1].startswith('yes') for line in result.stdout.splitlines())

    def package_manager_busy(self):
        """True when apt, dpkg or another updater holds the dpkg frontend lock."""
        if not self.paths.dpkg_lock.exists():
            return False
        with open(self.paths.dpkg_lock, 'a') as stream:
            try:
                fcntl.lockf(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return True
            fcntl.lockf(stream, fcntl.LOCK_UN)
        return False

    def session_healthy(self, processes):
        for name in processes:
            # The kernel truncates process names to 15 characters.
            if subprocess.run(['pgrep', '-x', name[:15]], capture_output=True).returncode != 0:
                return False
        return True

    def health_commands(self):
        directory = self.paths.health_dir
        return sorted(p for p in directory.glob('*') if p.is_file() and os.access(p, os.X_OK)) \
            if directory.is_dir() else []

    def run_health_command(self, command):
        result = subprocess.run([str(command)], capture_output=True, text=True, timeout=120, check=False)
        return result.returncode == 0, (result.stdout + result.stderr).strip()[-300:]


class Log:
    def __init__(self, path, echo=True):
        self.path, self.echo = Path(path), echo

    def __call__(self, level, message, **fields):
        line = f'{utcnow()} {level:<5} {message}'
        if fields:
            line += ' ' + ' '.join(f'{k}={v}' for k, v in fields.items())
        if self.echo:
            print(line, file=sys.stderr)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, 'a') as stream:
                stream.write(line + '\n')
        except OSError:
            pass  # logging must never decide whether an update is safe


class Updater:
    def __init__(self, paths, config, backend, system, log, sleep=time.sleep):
        self.paths, self.config, self.backend, self.system, self.log = paths, config, backend, system, log
        self.sleep = sleep

    # -- state ---------------------------------------------------------------

    def load(self):
        try:
            state = json.loads(self.paths.state_file.read_text())
        except FileNotFoundError:
            state = {}
        except ValueError as error:
            raise UpdateError(f'{self.paths.state_file} is unreadable ({error}); not touching the system') from None
        if state.get('schema', SCHEMA) > SCHEMA:
            raise UpdateError('state was written by a newer mseries-update; refusing to guess')
        state.setdefault('schema', SCHEMA)
        for key, empty in (('staged', None), ('journal', None), ('pending', None), ('last_applied', None),
                           ('last_check', None), ('skipped', {}), ('history', [])):
            state.setdefault(key, empty)
        return state

    def save(self, state):
        state['history'] = state['history'][-30:]
        write_atomic(self.paths.state_file, json.dumps(state, indent=2, sort_keys=True) + '\n')
        marker = self.paths.pending_marker
        if state['pending']:
            write_atomic(marker, state['pending']['id'] + '\n')
        else:
            marker.unlink(missing_ok=True)

    @contextlib.contextmanager
    def locked(self):
        self.paths.state.mkdir(parents=True, exist_ok=True)
        with open(self.paths.lock, 'a') as stream:
            try:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                raise Busy('another mseries-update is running') from None
            yield

    def record(self, state, outcome, transaction=None, detail=''):
        entry = {'time': utcnow(), 'outcome': outcome, 'detail': detail}
        if transaction:
            entry['id'] = transaction['id']
            entry['target'] = transaction['target']
        state['history'].append(entry)
        return entry

    # -- discovery -----------------------------------------------------------

    def updates(self, state, include_skipped=False):
        """{name: (installed, candidate)} for managed packages with a newer repo version."""
        installed = self.backend.installed(self.config.patterns)
        candidates = self.backend.candidates(list(installed))
        found = {}
        for name, version in installed.items():
            candidate = candidates.get(name)
            if not candidate or candidate == version or self.backend.compare(candidate, version) <= 0:
                continue
            if not include_skipped and candidate in state['skipped'].get(name, []):
                continue
            found[name] = (version, candidate)
        return found

    def check(self):
        with self.locked():
            state = self.load()
            self.backend.refresh()
            found = self.updates(state)
            state['last_check'] = {'time': utcnow(), 'channel': self.config.channel,
                                   'updates': {n: {'from': a, 'to': b} for n, (a, b) in found.items()}}
            self.save(state)
            self.log('INFO', f'check: {len(found)} update(s) on channel {self.config.channel}')
            return state['last_check']

    # -- preflight -----------------------------------------------------------

    def preflight(self, phase, size_bytes=0):
        """[(name, ok, severity, detail)]; severity 'defer' = try again next boot,
        'block' = needs attention. Only failures are acted on by the callers."""
        checks = []

        def add(name, ok, severity, detail):
            checks.append((name, bool(ok), severity, detail))

        needed = self.config.min_free_bytes + 3 * size_bytes
        for label, path in (('state', self.paths.state), ('system', Path('/usr'))) \
                if phase == 'apply' else (('state', self.paths.state),):
            free = self.system.free_bytes(path)
            add(f'disk:{label}', free >= needed, 'block',
                f'{free >> 20} MiB free, {needed >> 20} MiB needed')
        add('dpkg-lock', not self.system.package_manager_busy(), 'defer', 'apt or dpkg is running')
        audit = self.backend.audit()
        add('dpkg-audit', not audit, 'block', 'dpkg reports half-installed packages: ' + audit.replace('\n', ' ')[:200])
        if phase == 'stage':
            add('network', self.system.network_ok(), 'defer', 'update server is not reachable')
        else:
            source, percent = self.system.power()
            add('power', source == 'ac' or (percent is not None and percent >= self.config.min_battery), 'defer',
                f'on {source} at {percent}%, need AC or {self.config.min_battery}%')
        return checks

    def failed(self, checks):
        return [c for c in checks if not c[1]]

    # -- staging -------------------------------------------------------------

    def stage(self, include_skipped=False, automatic=False):
        with self.locked():
            state = self.load()
            if state['journal'] or state['pending']:
                raise UpdateError('an earlier update is still being recovered or confirmed; run: mseries-update status')
            if automatic and self.system.metered():
                self.log('INFO', 'stage: skipped, connection is metered')
                return None
            problems = self.failed(self.preflight('stage'))
            if problems:
                raise UpdateError('pre-flight failed: ' + '; '.join(f'{n} ({d})' for n, _, _, d in problems))
            self.backend.refresh()
            found = self.updates(state, include_skipped)
            if not found:
                if state['staged']:
                    self.discard_staged(state)
                    self.save(state)
                self.log('INFO', 'stage: already up to date')
                return None
            target = {name: new for name, (_, new) in found.items()}
            current = state['staged']
            if current and current['target'] == target and self.staged_intact(current):
                self.log('INFO', 'stage: update already staged', id=current['id'])
                return current
            if current:
                self.discard_staged(state)
            identity = hashlib.sha256(json.dumps(target, sort_keys=True).encode()).hexdigest()[:8]
            transaction_id = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + identity
            archives = self.paths.staged / transaction_id / 'archives'
            try:
                debs = self.backend.download([f'{n}={v}' for n, v in sorted(target.items())], archives)
                listing = []
                for deb in debs:
                    name, version = self.backend.deb_info(deb)
                    listing.append({'file': deb.name, 'name': name, 'version': version,
                                    'sha256': sha256_file(deb), 'size': deb.stat().st_size})
                downloaded = {entry['name']: entry['version'] for entry in listing}
                for name, version in target.items():
                    if downloaded.get(name) != version:
                        raise UpdateError(f'{name} {version} was not delivered by the repository')
                installed = self.backend.installed(['*'])
                self.ensure_rollback_material({e['name']: installed.get(e['name']) for e in listing})
            except BaseException:
                shutil.rmtree(self.paths.staged / transaction_id, ignore_errors=True)
                raise
            staged = {'id': transaction_id, 'created': utcnow(), 'channel': self.config.channel,
                      'target': target, 'from': {e['name']: installed.get(e['name']) for e in listing},
                      'debs': listing}
            state['staged'] = staged
            self.save(state)
            self.log('INFO', 'stage: update ready; it applies at the next restart', id=transaction_id,
                     packages=len(target), mib=sum(e['size'] for e in listing) >> 20)
            return staged

    def ensure_rollback_material(self, previous):
        """Make sure the exact versions we would roll back to are on disk before anything changes."""
        self.paths.store.mkdir(parents=True, exist_ok=True)
        for name, version in previous.items():
            if not version or self.backend.find_deb(name, version, [self.paths.store]):
                continue
            source = self.backend.find_deb(name, version, ['/var/cache/apt/archives'])
            if source and self.backend.deb_info(source) == (name, version):
                shutil.copy2(source, self.paths.store / source.name)
                continue
            try:
                downloaded = self.backend.download_exact(name, version, self.paths.store)
            except UpdateError as error:
                raise UpdateError(f'cannot stage: no rollback copy of {name} {version} ({error})') from None
            self.log('INFO', 'stage: fetched rollback copy', package=name, version=version, file=downloaded.name)

    def staged_intact(self, staged):
        archives = self.paths.staged / staged['id'] / 'archives'
        return all((archives / e['file']).is_file() and sha256_file(archives / e['file']) == e['sha256']
                   for e in staged['debs'])

    def discard_staged(self, state):
        if state['staged']:
            shutil.rmtree(self.paths.staged / state['staged']['id'], ignore_errors=True)
        state['staged'] = None

    # -- apply ---------------------------------------------------------------

    def apply(self):
        """Install the staged set as one dpkg run; on any failure converge back to the snapshot."""
        with self.locked():
            state = self.load()
            if state['journal']:
                self.recover(state)
            if state['pending']:
                raise UpdateError('the last update has not been confirmed yet; run: mseries-update status')
            staged = state['staged']
            if not staged:
                self.log('INFO', 'apply: nothing staged')
                return None
            if not self.staged_intact(staged):
                self.discard_staged(state)
                self.record(state, 'discarded', detail='staged files failed their checksum')
                self.save(state)
                self.log('ERROR', 'apply: staged files are damaged or missing; discarded, nothing installed')
                raise UpdateError('staged files failed verification; run: mseries-update stage')
            blocked = self.failed(self.preflight('apply', sum(e['size'] for e in staged['debs'])))
            if blocked:
                text = '; '.join(f'{n} ({d})' for n, _, _, d in blocked)
                if all(severity == 'defer' for _, _, severity, _ in blocked):
                    self.log('WARN', 'apply: deferred to a later restart', reasons=text)
                    return {'deferred': text}
                self.log('ERROR', 'apply: pre-flight failed, nothing installed', reasons=text)
                raise UpdateError('pre-flight failed: ' + text)
            installed = self.backend.installed(['*'])
            snapshot = {e['name']: installed.get(e['name']) for e in staged['debs']}
            missing = [f'{n} {v}' for n, v in snapshot.items()
                       if v and not self.backend.find_deb(n, v, [self.paths.store])]
            if missing:
                self.log('ERROR', 'apply: rollback copies are missing, nothing installed', packages=', '.join(missing))
                raise UpdateError('rollback copies missing for ' + ', '.join(missing) + '; run: mseries-update stage')
            archives = self.paths.staged / staged['id'] / 'archives'
            # Write-ahead journal: if power fails mid-install the next boot restores `restore`.
            state['journal'] = {'id': staged['id'], 'kind': 'apply', 'started': utcnow(),
                                'restore': snapshot, 'target': staged['target']}
            self.save(state)
            self.log('INFO', 'apply: installing', id=staged['id'], packages=len(staged['debs']))
            failure = None
            try:
                self.backend.install_debs([archives / e['file'] for e in staged['debs']])
                failure = self.health_failures(staged)
            except UpdateError as error:
                failure = [str(error)]
            if failure:
                self.log('ERROR', 'apply: failed, restoring the previous set', reasons=' | '.join(failure)[:400])
                self.converge(snapshot)
                self.skip(state, staged['target'])
                self.record(state, 'rolled-back', staged, '; '.join(failure)[:300])
                state['journal'] = None
                self.discard_staged(state)
                state['last_applied'] = None
                self.save(state)
                return {'rolled_back': True, 'reasons': failure}
            for entry in staged['debs']:
                shutil.copy2(archives / entry['file'], self.paths.store / entry['file'])
            state['journal'] = None
            state['pending'] = {'id': staged['id'], 'applied': utcnow(), 'unconfirmed_boots': 0}
            state['last_applied'] = {'id': staged['id'], 'from': snapshot, 'to': {e['name']: e['version'] for e in staged['debs']},
                                     'applied': utcnow(), 'confirmed': None, 'rolled_back': None}
            self.discard_staged(state)
            self.record(state, 'applied', staged)
            self.save(state)
            self.log('INFO', 'apply: installed; waiting for a healthy login to confirm', id=staged['id'])
            return {'applied': staged['target']}

    def health_failures(self, staged):
        names = [e['name'] for e in staged['debs']]
        installed = self.backend.installed(['*'])
        problems = [f'{e["name"]} is {installed.get(e["name"])}, expected {e["version"]}'
                    for e in staged['debs'] if installed.get(e['name']) != e['version']]
        problems += self.backend.verify(names)
        for command in self.system.health_commands():
            ok, output = self.system.run_health_command(command)
            if not ok:
                problems.append(f'health check {command.name} failed: {output}')
        return problems

    def converge(self, restore):
        """Idempotently make the installed versions equal `restore` (name -> version or None)."""
        installed = self.backend.installed(['*'])
        reinstall = [name for name, version in restore.items() if version and installed.get(name) != version]
        remove = [name for name, version in restore.items() if not version and name in installed]
        debs = []
        for name in reinstall:
            deb = self.backend.find_deb(name, restore[name], [self.paths.store])
            if not deb:
                raise RollbackFailed(f'rollback copy of {name} {restore[name]} is missing')
            debs.append(deb)
        try:
            self.backend.remove(remove)
            if debs:
                self.backend.install_debs(debs)
        except UpdateError as error:
            raise RollbackFailed(f'restoring the previous set failed: {error}') from None
        installed = self.backend.installed(['*'])
        wrong = [f'{n} (have {installed.get(n)}, want {v})' for n, v in restore.items() if installed.get(n) != v]
        if wrong:
            raise RollbackFailed('previous set not fully restored: ' + ', '.join(wrong))

    def skip(self, state, target):
        for name, version in target.items():
            versions = state['skipped'].setdefault(name, [])
            if version not in versions:
                versions.append(version)

    def recover(self, state):
        """Finish or undo a transaction that a crash or power loss interrupted."""
        journal = state['journal']
        self.log('WARN', f'recover: {journal["kind"]} {journal["id"]} was interrupted; restoring the previous set')
        try:
            self.converge(journal['restore'])
        except RollbackFailed as error:
            state['journal'] = journal | {'failed': str(error)}
            self.record(state, 'rollback-failed', journal, str(error))
            self.save(state)
            self.log('ERROR', f'recover: {error}')
            raise
        if journal['kind'] == 'apply':
            self.skip(state, journal['target'])
        self.record(state, 'recovered', journal, 'interrupted ' + journal['kind'])
        state['journal'] = None
        if journal['kind'] == 'apply':
            state['pending'] = None
            state['last_applied'] = None
        self.discard_staged(state)
        self.save(state)

    # -- rollback and confirmation -------------------------------------------

    def rollback(self, reason='requested'):
        with self.locked():
            state = self.load()
            if state['journal']:
                self.recover(state)
                return {'recovered': True}
            applied = state['last_applied']
            if not applied or applied['rolled_back']:
                raise UpdateError('there is no applied update to roll back')
            self.do_rollback(state, applied, reason)
            return {'restored': applied['from']}

    def do_rollback(self, state, applied, reason):
        self.log('WARN', 'rollback: restoring the previous set', id=applied['id'], reason=reason)
        journal = {'id': applied['id'], 'kind': 'rollback', 'started': utcnow(),
                   'restore': applied['from'], 'target': applied['to']}
        state['journal'] = journal
        self.save(state)
        try:
            self.converge(applied['from'])
        except RollbackFailed as error:
            self.record(state, 'rollback-failed', journal, str(error))
            self.save(state)
            self.log('ERROR', f'rollback: {error}')
            raise
        self.skip(state, applied['to'])
        applied['rolled_back'] = utcnow()
        state['journal'] = None
        state['pending'] = None
        self.record(state, 'rolled-back', journal, reason)
        self.save(state)
        self.log('INFO', 'rollback: previous set restored; it is active at the next login', id=applied['id'])

    def confirm(self, wait=0):
        """Mark the new set known-good once a healthy graphical session exists."""
        with self.locked():
            state = self.load()
            pending = state['pending']
            if not pending:
                return {'confirmed': None}
            deadline = time.monotonic() + wait
            while not self.system.session_healthy(self.config.session_processes):
                if time.monotonic() >= deadline:
                    self.log('WARN', 'confirm: no healthy session yet; update stays unconfirmed')
                    return {'confirmed': False}
                self.sleep(5)
            state['last_applied']['confirmed'] = utcnow()
            state['pending'] = None
            self.record(state, 'confirmed', detail='healthy session')
            self.save(state)
            self.prune_store(state)
            self.log('INFO', 'confirm: the update set is now known-good', id=pending['id'])
            return {'confirmed': True}

    def prune_store(self, state):
        keep = set()
        applied = state['last_applied'] or {}
        for key in ('from', 'to'):
            for name, version in (applied.get(key) or {}).items():
                if version:
                    deb = self.backend.find_deb(name, version, [self.paths.store])
                    keep.add(deb.name if deb else None)
        if self.paths.store.is_dir():
            for deb in self.paths.store.glob('*.deb'):
                if deb.name not in keep:
                    deb.unlink()

    def boot(self):
        """Early-boot entry point; always leaves the machine on a complete package set."""
        with self.locked():
            state = self.load()
            if state['journal']:
                self.recover(state)
            pending = state['pending']
            if pending:
                pending['unconfirmed_boots'] += 1
                if pending['unconfirmed_boots'] >= self.config.max_unconfirmed_boots:
                    self.do_rollback(state, state['last_applied'],
                                     f'no healthy login after {pending["unconfirmed_boots"]} restarts')
                else:
                    self.save(state)
                    self.log('WARN', 'boot: previous update not confirmed yet',
                             restarts=pending['unconfirmed_boots'], limit=self.config.max_unconfirmed_boots)
                return {'pending': True}
        return self.apply() if self.load()['staged'] else {'idle': True}

    # -- reporting -----------------------------------------------------------

    def status(self):
        state = self.load()
        power, percent = self.system.power()
        return {
            'schema': SCHEMA,
            'channel': self.config.channel,
            'auto_stage': self.config.auto_stage,
            'state': ('recovering' if state['journal'] else 'awaiting-confirmation' if state['pending']
                      else 'staged' if state['staged'] else 'idle'),
            'staged': state['staged'] and {k: state['staged'][k] for k in ('id', 'created', 'channel', 'target', 'from')},
            'pending_confirmation': state['pending'],
            'last_applied': state['last_applied'],
            'last_check': state['last_check'],
            'skipped': state['skipped'],
            'last_result': state['history'][-1] if state['history'] else None,
            'power': {'source': power, 'percent': percent},
        }

    def automatic(self):
        """Timer entry: always check; stage only when the owner turned auto_stage on."""
        found = self.check()
        if found['updates'] and self.config.auto_stage:
            self.stage(automatic=True)
        return found


def source_file(uri, channel, keyring):
    return ('# Managed by mseries-update. Private to the updater: system apt does not read this file.\n'
            'Types: deb\n'
            f'URIs: {uri}\n'
            f'Suites: {channel}\n'
            'Components: main\n'
            'Architectures: arm64\n'
            f'Signed-By: {keyring}\n')


def write_sources(paths, uri, channel, keyring):
    if not Path(keyring).is_file():
        raise UpdateError(f'keyring {keyring} not found')
    if not re.fullmatch(r'(https://|file:/)\S+', uri):
        raise UpdateError('the update URI must be https:// (or file:/ for a local mirror)')
    write_atomic(paths.sources_file, source_file(uri, channel, keyring))


def read_source(paths):
    text = paths.sources_file.read_text() if paths.sources_file.exists() else ''
    fields = dict(re.findall(r'^(URIs|Signed-By):\s*(\S+)', text, re.MULTILINE))
    return fields.get('URIs'), fields.get('Signed-By')


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0],
                                     epilog='Design: mseries/UPDATER-DESIGN.md')
    parser.add_argument('--quiet', action='store_true', help='log to the file only')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check', help='refresh signed metadata and list available updates')
    stage = commands.add_parser('stage', help='download and verify an update; installs nothing')
    stage.add_argument('--include-skipped', action='store_true', help='retry versions that were rolled back')
    apply = commands.add_parser('apply', help='install the staged update now instead of at the next restart')
    apply.add_argument('--now', action='store_true',
                       help='required: files change under the running session, which keeps its old copies until next login')
    commands.add_parser('boot', help='systemd entry point at startup')
    confirm = commands.add_parser('confirm', help='confirm the update after a healthy login')
    confirm.add_argument('--wait', type=int, default=None, help='seconds to wait for the session')
    commands.add_parser('rollback', help='restore the package set from before the last update')
    commands.add_parser('auto', help='timer entry: check, and stage if auto_stage is on')
    status = commands.add_parser('status', help='show update state')
    status.add_argument('--json', action='store_true')
    log = commands.add_parser('log', help='show the update log')
    log.add_argument('-n', type=int, default=40)
    init = commands.add_parser('init', help='configure the signed update repository')
    init.add_argument('--uri', required=True)
    init.add_argument('--keyring', required=True)
    init.add_argument('--channel', choices=CHANNELS, default='stable')
    channel = commands.add_parser('channel', help='show or switch the update channel')
    channel.add_argument('name', nargs='?', choices=CHANNELS)
    setting = commands.add_parser('config', help='show or change a setting')
    setting.add_argument('key', nargs='?')
    setting.add_argument('value', nargs='?')
    return parser


MUTATING = {'check', 'stage', 'apply', 'boot', 'confirm', 'rollback', 'auto', 'init', 'channel'}


def main(argv=None, paths=None, backend=None, system=None):
    args = build_parser().parse_args(argv)
    paths = paths or Paths()
    try:
        if args.command in MUTATING and os.geteuid() != 0 and not os.environ.get('MSERIES_UPDATE_ALLOW_NONROOT'):
            raise UpdateError(f'"{args.command}" needs root: sudo mseries-update {args.command}')
        config = Config(paths.config)
        log = Log(paths.log, echo=not args.quiet)
        updater = Updater(paths, config, backend or Backend(paths), system or System(paths), log)
        if args.command == 'init':
            write_sources(paths, args.uri, args.channel, args.keyring)
            if args.channel != config.channel:
                config.set('channel', args.channel)
            print(f'Update source set: {args.uri} ({args.channel}). Next: sudo mseries-update check')
        elif args.command == 'channel':
            if args.name:
                uri, keyring = read_source(paths)
                if not uri:
                    raise UpdateError('run mseries-update init first')
                with updater.locked():
                    state = updater.load()
                    if state['journal'] or state['pending']:
                        raise UpdateError('finish or roll back the current update before switching channel')
                    write_sources(paths, uri, args.name, keyring)
                    config.set('channel', args.name)
                    updater.discard_staged(state)
                    state['skipped'] = {}
                    updater.save(state)
            print(Config(paths.config).channel)
        elif args.command == 'config':
            if args.key and args.value is not None:
                if os.geteuid() != 0 and not os.environ.get('MSERIES_UPDATE_ALLOW_NONROOT'):
                    raise UpdateError('changing settings needs root: sudo mseries-update config KEY VALUE')
                config.set(args.key, args.value)
            elif args.key:
                print(config.values.get(args.key, ''))
            else:
                for key, value in config.values.items():
                    print(f'{key} = {value}')
        elif args.command == 'status':
            report = updater.status()
            if args.json:
                print(json.dumps(report, indent=2, sort_keys=True))
            else:
                print_status(report)
        elif args.command == 'log':
            lines = paths.log.read_text().splitlines() if paths.log.exists() else []
            print('\n'.join(lines[-args.n:]))
        elif args.command == 'check':
            found = updater.check()
            print(json.dumps(found, indent=2, sort_keys=True))
        elif args.command == 'auto':
            updater.automatic()
        elif args.command == 'stage':
            staged = updater.stage(include_skipped=args.include_skipped)
            print('Update staged; it will be installed at the next restart.' if staged else 'Already up to date.')
        elif args.command == 'apply':
            if not args.now:
                raise UpdateError('updates install at the next restart; pass --now to install immediately '
                                  '(the running desktop keeps its old copies until next login)')
            result = updater.apply()
            print(json.dumps(result, indent=2, sort_keys=True))
            if result and result.get('rolled_back'):
                return EXIT_FAILED
        elif args.command == 'boot':
            result = updater.boot()
            if result and result.get('rolled_back'):
                return EXIT_FAILED
        elif args.command == 'confirm':
            result = updater.confirm(config.confirm_timeout if args.wait is None else args.wait)
            print(json.dumps(result))
            return 0 if result['confirmed'] is not False else EXIT_FAILED
        elif args.command == 'rollback':
            print(json.dumps(updater.rollback(), indent=2, sort_keys=True))
        return 0
    except RollbackFailed as error:
        print(f'mseries-update: ROLLBACK FAILED, the package set needs attention: {error}', file=sys.stderr)
        return EXIT_ROLLBACK_FAILED
    except Busy as error:
        print(f'mseries-update: {error}', file=sys.stderr)
        return EXIT_BUSY
    except UpdateError as error:
        print(f'mseries-update: {error}', file=sys.stderr)
        return EXIT_FAILED


def print_status(report):
    print(f'Channel: {report["channel"]}    State: {report["state"]}')
    check = report['last_check']
    if check:
        print(f'Last check: {check["time"]}, {len(check["updates"])} update(s) available')
    if report['staged']:
        print('Staged (installs at next restart): ' + ', '.join(f'{n} {v}' for n, v in report['staged']['target'].items()))
    if report['pending_confirmation']:
        print('Installed, waiting for a healthy login to confirm: ' + report['pending_confirmation']['id'])
    result = report['last_result']
    if result:
        print(f'Last result: {result["outcome"]} at {result["time"]} {result["detail"]}'.rstrip())


if __name__ == '__main__':
    sys.exit(main())
