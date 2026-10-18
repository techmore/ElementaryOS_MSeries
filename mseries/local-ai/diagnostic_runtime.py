"""Owned, on-demand diagnostic worker; no inference or service work on import.

Explicit exclusive sessions may release only an idle, enabled everyday 4B.
Three idle checks narrow but cannot eliminate a new-client-after-check race;
TCP observation is not a transactional reservation of another application's UI.
"""
from contextlib import contextmanager
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import socket
import select
import signal
import stat
import subprocess
import time
import urllib.request
import uuid

from machine import GIB, runtime_prefix, snapshot

ENDPOINT = 'http://127.0.0.1:8772'
MODEL_REPO = 'mlx-community/Qwen3.5-9B-MLX-4bit'
MODEL_REVISION = '938d8919941c6e7efd3c7150eff7fe9d12afa631'
DIAGNOSTIC = 'mseries-ai-diagnostic.service'
EVERYDAY = 'mseries-ai-everyday.service'
KNOWN_UNITS = {f'mseries-ai-{name}.service' for name in (
    'everyday', 'quality', 'coder9', 'compact', 'personal', 'coder', 'coder7',
    'coder-large', 'liquid', 'bonsai', 'compact35', 'diagnostic')}
ACTIVE = {'active', 'activating', 'reloading', 'deactivating'}
RACE_LIMITATION = 'Idle observations cannot exclude a new everyday client connecting after the final check.'
# A fixed systemd unit cannot attribute a successful StartUnit to this caller
# when an owner starts it concurrently. Keep runtime OFF until a uniquely
# attributable launch mechanism is implemented and independently reviewed.
OWNED_START_READY = False
ACCEPTANCE_SCHEMA = 'mseries.diagnostic.acceptance.v1'
QUALIFICATION_SOURCES = ('diagnostic_contract.py', 'diagnostic_agent.py', 'diagnostic_runtime.py',
                         'diagnostic-qualification.py', 'machine.py', 'model-worker.py', 'runtime_recovery.py')


class Deferred(ValueError):
    """Evidence is retained; a safe diagnostic session cannot start now."""


def config_path():
    return Path.home() / '.config/mseries-ai/diagnostic-profile.json'


def worker_path():
    return Path.home() / '.local/libexec/mseries-ai/model-worker.py'


def snapshot_path():
    return Path.home() / '.cache/huggingface/hub' / ('models--' + MODEL_REPO.replace('/', '--')) / 'snapshots' / MODEL_REVISION


def _private_bytes(path, *, private=False, max_bytes=256 * 1024):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if (info.st_uid != os.getuid() or not stat.S_ISREG(info.st_mode) or info.st_size > max_bytes
                or (private and stat.S_IMODE(info.st_mode) & 0o077)):
            raise Deferred('Unsafe or oversized diagnostic configuration')
        with os.fdopen(fd, 'rb') as stream:
            fd = -1
            raw = stream.read(max_bytes + 1)
            if len(raw) > max_bytes:
                raise Deferred('Diagnostic JSON exceeded its bound')
            return raw
    finally:
        if fd >= 0:
            os.close(fd)


def _private_json(path, *, private=False, max_bytes=256 * 1024):
    value = json.loads(_private_bytes(path, private=private, max_bytes=max_bytes))
    if not isinstance(value, dict):
        raise Deferred('Diagnostic JSON must be an object')
    return value


def read_config():
    config = _private_json(config_path())
    profile = config.get('profiles', {}).get('diagnostic', {})
    if (profile.get('engine') != 'mlx' or profile.get('model') != 'qwen3.5-9b-mlx-4bit'
            or profile.get('port') != 8772 or profile.get('context') not in (4096, 8192)
            or not isinstance(profile.get('admission_gib'), (int, float))
            or isinstance(profile.get('admission_gib'), bool) or not math.isfinite(profile['admission_gib'])
            or profile['admission_gib'] < 9):
        raise Deferred('Diagnostic profile must use the pinned 9B, isolated port, bounded context and nine-GiB admission')
    model = snapshot_path()
    if not (model / 'config.json').is_file() or not list(model.glob('*.safetensors')):
        raise Deferred('Pinned diagnostic model assets are absent')
    return config


def _digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def _model_manifest(directory):
    """Hash actual assets, allowing only normal HF blob links inside this repo."""
    repository = directory.parent.parent.resolve(strict=True)
    files = sorted(path for path in directory.rglob('*') if path.is_file() or path.is_symlink())
    if not 1 <= len(files) <= 64:
        raise Deferred('Pinned model file manifest is absent or oversized')
    result, observed, total = {}, [], 0
    for path in files:
        target = path.resolve(strict=True)
        if (not target.is_relative_to(repository) or (path.is_symlink()
                and (target.parent != repository / 'blobs' or not re.fullmatch(r'[0-9a-f]{40}|[0-9a-f]{64}', target.name)))):
            raise Deferred('Pinned model asset is outside its repository or is not a normal HF blob link')
        before = target.stat()
        total += before.st_size
        if not stat.S_ISREG(before.st_mode) or before.st_size > 8 * GIB or total > 12 * GIB:
            raise Deferred('Pinned model asset is not a bounded regular file')
        stamp = lambda row: (row.st_dev, row.st_ino, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
        result[str(path.relative_to(directory))] = _digest(target)
        observed.append((target, stamp(before)))
        if stamp(target.stat()) != stamp(before):
            raise Deferred('Pinned model changed while its identity was read')
    if any(stamp(path.stat()) != before for path, before in observed):
        raise Deferred('Pinned model changed while its identity was read')
    required = {'config.json', 'tokenizer.json', 'tokenizer_config.json', 'model.safetensors.index.json'}
    if not required <= result.keys():
        raise Deferred('Pinned model configuration/tokenizer/index is incomplete')
    index_path = directory / 'model.safetensors.index.json'
    if index_path.stat().st_size > 4 * 1024 * 1024:
        raise Deferred('Pinned model shard index is oversized')
    index_raw = index_path.read_bytes()
    if hashlib.sha256(index_raw).hexdigest() != result['model.safetensors.index.json']:
        raise Deferred('Pinned model index changed while its identity was read')
    index = json.loads(index_raw)
    weights = index.get('weight_map') if isinstance(index, dict) else None
    shards = list(weights.values()) if isinstance(weights, dict) else []
    if not shards or any(not isinstance(name, str) or Path(name).name != name or not name.endswith('.safetensors') or name not in result for name in shards):
        raise Deferred('Pinned model index references an unavailable or unsafe shard')
    return result


def _fixture_manifest(directory):
    paths = sorted(directory.glob('*.json'))
    if not 1 <= len(paths) <= 64:
        raise Deferred('Diagnostic acceptance fixture set is unavailable')
    result = {}
    for path in paths:
        raw = _private_bytes(path)
        case = json.loads(raw)
        if not isinstance(case, dict):
            raise Deferred('Diagnostic acceptance fixture must be an object')
        if (case.get('case_id') != path.stem or case.get('fixture_schema_version') != 'mseries.diagnostic.fixture.v1'
                or case.get('split') not in {'core', 'heldout'}):
            raise Deferred('Diagnostic acceptance fixture identity is invalid')
        result[path.stem] = hashlib.sha256(raw).hexdigest()
    return result


def qualification_identity():
    """Identity required in an accepted, private diagnostic qualification receipt."""
    read_config()
    prefix = runtime_prefix()
    libraries = list((prefix / 'venv/lib').glob('python*/site-packages/mlx/lib/libmlx.so'))
    if len(libraries) != 1:
        raise Deferred('Cannot identify the installed diagnostic runtime library')
    source = worker_path().parent
    return {'model_repo': MODEL_REPO, 'model_revision': MODEL_REVISION,
            'model_files_sha256': _model_manifest(snapshot_path()),
            'source_sha256': {name: _digest(source / name) for name in QUALIFICATION_SOURCES},
            'fixtures_sha256': _fixture_manifest(source / 'fixtures/diagnostic'),
            'profile_sha256': _digest(config_path()), 'worker_sha256': _digest(worker_path()),
            'global_profiles_sha256': _digest(Path.home() / '.config/mseries-ai/profiles.json'),
            'runtime_module_sha256': _digest(Path(__file__)),
            'machine_sha256': _digest(worker_path().with_name('machine.py')),
            'runtime_sha256': _digest(libraries[0]), 'kernel': os.uname().release}


def _canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def require_qualified():
    """A manual decision binds an immutable complete report, not automatic passes."""
    path = Path.home() / '.local/state/mseries-troubleshooter/diagnostic-qualification.json'
    try:
        receipt = _private_json(path, private=True)
        identity = qualification_identity()
        if (receipt.get('schema_version') != ACCEPTANCE_SCHEMA or receipt.get('qualified') is not True
                or receipt.get('identity') != identity):
            raise Deferred('Diagnostic model is not qualified for this exact source, model bytes, runtime, kernel and policy')
        reference, decision = receipt.get('report'), receipt.get('decision')
        if not isinstance(reference, dict) or not isinstance(decision, dict):
            raise Deferred('Accepted diagnosis needs a report and independent semantic decision')
        name = reference.get('file')
        if not isinstance(name, str) or Path(name).name != name or not name.endswith('.json'):
            raise Deferred('Accepted diagnosis needs a local reviewed qualification report')
        report_path = path.parent / name
        # Read and hash the same bounded private bytes; never follow a report link.
        raw = _private_bytes(report_path, private=True, max_bytes=4 * 1024 * 1024)
        report_hash = hashlib.sha256(raw).hexdigest()
        report = json.loads(raw)
        if not isinstance(report, dict):
            raise Deferred('Reviewed report must be an object')
        cases = sorted(identity['fixtures_sha256'])
        if (reference.get('sha256') != report_hash or decision.get('verdict') != 'accepted'
                or decision.get('reviewed_report_sha256') != report_hash
                or decision.get('reviewed_identity_sha256') != _canonical_hash(identity)
                or decision.get('reviewed_cases') != cases
                or not isinstance(decision.get('reviewer'), str) or not 1 <= len(decision['reviewer'].strip()) <= 128):
            raise Deferred('Independent semantic acceptance is missing or does not bind this report/identity')
        recorded, metadata = report.get('identity'), report.get('metadata')
        if not isinstance(recorded, dict) or not isinstance(metadata, dict):
            raise Deferred('Reviewed report identity is unavailable')
        repeat = recorded.get('repeat')
        count = len(cases) * repeat if type(repeat) is int and 1 <= repeat <= 3 else 0
        if (report.get('schema_version') != 'mseries.diagnostic.qualification.v1'
                or report.get('frozen_integrity_error') or report.get('qualified') is not False
                or report.get('complete') is not True or report.get('quiet_policy_passed') is not True
                or not count or report.get('completed_trials') != count or report.get('automatic_passes') != count
                or recorded.get('split') != 'all' or recorded.get('endpoint') != ENDPOINT
                or recorded.get('kernel') != identity['kernel']
                or recorded.get('metadata_sha256') != _canonical_hash(metadata)
                or recorded.get('source_sha256') != identity['source_sha256']
                or recorded.get('fixtures_sha256') != identity['fixtures_sha256']
                or metadata.get('acceptance_identity') != identity):
            raise Deferred('The reviewed report does not complete the exact source/model/fixture qualification')
        trials = report.get('trials')
        if not isinstance(trials, list) or len(trials) != count:
            raise Deferred('Reviewed qualification trials are incomplete')
        expected = {(case, number) for case in cases for number in range(repeat)}
        seen = set()
        for trial in trials:
            if not isinstance(trial, dict) or type(trial.get('repeat')) is not int:
                raise Deferred('Reviewed qualification trial is invalid')
            key = (trial.get('case_id'), trial['repeat'])
            if key not in expected or key in seen or trial.get('status') != 'completed' or trial.get('automatic_pass') is not True:
                raise Deferred('Reviewed qualification trials are incomplete or include a preserved quality failure')
            seen.add(key)
            attempts = trial.get('attempts')
            last = attempts[-1] if isinstance(attempts, list) and attempts else {}
            if not isinstance(last, dict):
                raise Deferred('Reviewed qualification attempt is invalid')
            resources = last.get('resources', {})
            if (not isinstance(resources, dict) or last.get('status') != 'completed'
                    or last.get('quality_scored') is not True or resources.get('quiet_policy_passed') is not True
                    or resources.get('telemetry_complete') is not True):
                raise Deferred('Reviewed qualification contains unscored or inadequately observed final attempts')
    except (OSError, ValueError, TypeError, KeyError) as error:
        if isinstance(error, Deferred):
            raise
        raise Deferred('Diagnostic qualification is unavailable; use evidence collection until qualification finishes') from error


def _run(*args):
    result = subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise Deferred('Owned diagnostic service operation failed: ' + args[0])
    return result.stdout


def unit_info(unit):
    raw = _run('show', unit, '--property=Id,LoadState,ActiveState,MainPID,ExecStart,FragmentPath,UnitFileState,InvocationID,Job,Restart')
    row = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
    try:
        row['MainPID'] = int(row.get('MainPID', '0'))
    except ValueError as error:
        raise Deferred('Invalid service process identity') from error
    if row.get('LoadState') != 'loaded':
        raise Deferred('Required managed model unit is not installed: ' + unit)
    return row


def managed_units():
    raw = _run('list-units', '--all', '--plain', '--no-legend', 'mseries-ai-*.service')
    return KNOWN_UNITS | {line.split()[0] for line in raw.splitlines() if line.split()}


def _command_matches(command, profile):
    expected = ['/usr/bin/python3', str(worker_path()), profile]
    if profile == 'diagnostic':
        expected += ['--config', str(config_path())]
    return command == expected


def _validate_unit(unit, row, *, running=False):
    profile = 'diagnostic' if unit == DIAGNOSTIC else 'everyday'
    expected_file = Path.home() / '.config/systemd/user' / unit
    if row.get('FragmentPath') != str(expected_file):
        raise Deferred('Managed service file ownership does not match the installed unit')
    match = re.search(r'argv\[\]=(.*?)\s*;', row.get('ExecStart', ''))
    if not match or not _command_matches(shlex.split(match.group(1)), profile):
        raise Deferred('Managed service command does not match the expected worker/configuration')
    if running:
        pid = row['MainPID']
        if not pid:
            raise Deferred('Active managed model has no process identity')
        command = (Path('/proc') / str(pid) / 'cmdline').read_bytes().rstrip(b'\0').decode().split('\0')
        if not _command_matches(command, profile):
            raise Deferred('Running model process does not match the managed service')
        return _process_identity(pid)
    return None


def _process_identity(pid):
    directory = Path('/proc') / str(pid)
    if directory.stat().st_uid != os.getuid():
        raise Deferred('Model process belongs to another user')
    # starttime excludes reuse of a recycled PID between observation and cleanup.
    return (pid, (directory / 'stat').read_text().rsplit(')', 1)[1].split()[19])


def _same_process(unit, identity):
    try:
        row = unit_info(unit)
        return row['MainPID'] == identity[0] and _validate_unit(unit, row, running=True) == identity
    except (OSError, ValueError):
        return False


def _other_active():
    active = []
    for unit in sorted(managed_units() - {DIAGNOSTIC, EVERYDAY}):
        try:
            row = unit_info(unit)
        except Deferred as error:
            # Known profiles can be absent on a minimal install. Unknown live
            # units from list-units still fail closed if their state is unreadable.
            if unit in KNOWN_UNITS and str(error).startswith('Required managed model unit is not installed:'):
                continue
            raise
        if row.get('ActiveState') in ACTIVE:
            active.append(unit)
    return active


def _established_local(port=8766, proc=Path('/proc/net')):
    for name in ('tcp', 'tcp6'):
        text = (proc / name).read_text()
        for line in text.splitlines()[1:]:
            fields = line.split()
            if len(fields) < 4 or fields[3] != '01':
                continue
            # Conservative: any established socket involving the local model
            # port blocks release, including IPv6/mapped-loopback clients.
            if any(int(fields[index].rsplit(':', 1)[1], 16) == port for index in (1, 2)):
                return True
    return False


def _f5_idle():
    raw = _run('show', 'mseries-stream-dictate.service', '--property=ActiveState,MainPID')
    row = dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)
    if row.get('ActiveState') not in ACTIVE:
        return True
    status_file = Path(os.environ.get('XDG_RUNTIME_DIR', f'/run/user/{os.getuid()}')) / 'mseries-dictation/status.json'
    try:
        status_row = _private_json(status_file, private=True)
        pid = int(row.get('MainPID', '0'))
        _process_identity(pid)
        return (pid > 0 and status_row.get('pid') == pid
                and status_row.get('phase') in {'ready', 'waiting', 'error', 'cancelled', 'stopped'})
    except (OSError, ValueError):
        return False


def speech_idle():
    """Public guard shared by the diagnostic supervisor and session manager."""
    return _f5_idle()


def quiet_reasons(extra_bytes=0, *, admission=False):
    try:
        measured = snapshot()
        fans, temps = measured['fans_rpm'], measured['temperatures_c']
        reasons = []
        if (not fans or not temps or any(not isinstance(value, (int, float)) or not math.isfinite(value)
                or value < 0 for value in [*fans.values(), *temps.values()])):
            reasons.append('fan or temperature telemetry is unavailable')
        fan_limit, temp_limit = (2600, 58) if admission else (2700, 63)
        config = read_config()
        for policy in (config.get('policy', {}), config['profiles']['diagnostic'].get('policy', {})):
            fan_limit = min(fan_limit, policy.get('admission_fan_rpm' if admission else 'max_fan_rpm', fan_limit))
            temp_limit = min(temp_limit, policy.get('admission_temp_c' if admission else 'max_temp_c', temp_limit))
        if max(fans.values(), default=0) >= fan_limit:
            reasons.append('fan guard requires a quieter window')
        if max(temps.values(), default=0) >= temp_limit:
            reasons.append('temperature guard requires a cooler window')
        reserve = 6
        reserve = max(reserve, config.get('policy', {}).get('reserve_gib', 6),
                      config['profiles']['diagnostic'].get('policy', {}).get('reserve_gib', 6))
        global_config = Path.home() / '.config/mseries-ai/profiles.json'
        if global_config.exists():
            reserve = max(reserve, _private_json(global_config).get('policy', {}).get('reserve_gib', 6))
        if not math.isfinite(reserve):
            raise Deferred('Invalid desktop memory reserve')
        if measured['available_bytes'] - extra_bytes < reserve * GIB:
            reasons.append('six-GiB desktop reserve would be crossed')
        return reasons
    except (OSError, ValueError, KeyError, TypeError) as error:
        return ['quiet admission cannot be established: ' + str(error)[:160]]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise Deferred('Diagnostic inference redirects are refused')


def _request(endpoint, path, payload=None, timeout=5):
    if endpoint.rstrip('/') != ENDPOINT or path not in {'/v1/models', '/v1/chat/completions'}:
        raise Deferred('Only the dedicated numeric-loopback diagnostic endpoint is allowed')
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), _NoRedirect())
    data = None if payload is None else json.dumps(payload).encode()
    request = urllib.request.Request(ENDPOINT + path, data=data, headers={'Content-Type': 'application/json'})
    with opener.open(request, timeout=min(600, max(1, timeout))) as response:
        raw = response.read(2 * 1024 * 1024 + 1)
    if len(raw) > 2 * 1024 * 1024:
        raise Deferred('Diagnostic response exceeded its bound')
    result = json.loads(raw)
    if not isinstance(result, dict):
        raise Deferred('Invalid diagnostic response')
    return result


def verify_model(endpoint=ENDPOINT):
    expected = str(snapshot_path())
    models = _request(endpoint, '/v1/models').get('data', [])
    ids = [row.get('id') for row in models if isinstance(row, dict)]
    # mlx-lm 0.31.3 lists cached repo aliases and then the configured absolute
    # model path. Cache aliases do not establish the loaded identity.
    absolute = [value for value in ids if isinstance(value, str) and value.startswith('/')]
    if absolute != [expected]:
        raise Deferred('The isolated diagnostic endpoint is not serving exactly the pinned 9B snapshot')
    return expected


def api(endpoint, path, payload=None, timeout=5):
    if path == '/v1/chat/completions':
        model = verify_model(endpoint)
        if not isinstance(payload, dict) or payload.get('model') != model:
            raise Deferred('Diagnostic request must name the verified pinned snapshot')
        reasons = quiet_reasons()
        if reasons or not _f5_idle():
            raise Deferred('; '.join(reasons or ['F5 is busy or its state is unavailable']))
    return _request(endpoint, path, payload, timeout)


def _port_free(port=8772):
    with socket.socket() as sock:
        try:
            sock.bind(('127.0.0.1', port))
        except OSError as error:
            raise Deferred('The isolated diagnostic port is already occupied') from error


def _idle_checks(identity):
    for number in range(3):
        if (not _same_process(EVERYDAY, identity) or _other_active()
                or _established_local() or not _f5_idle()):
            raise Deferred('Everyday model is busy, changed ownership, or F5 is active; diagnosis is deferred')
        reasons = quiet_reasons(admission=True)
        if reasons:
            raise Deferred('; '.join(reasons))
        if number < 2:
            time.sleep(.25)


def _restore_everyday(lifecycle):
    try:
        row = unit_info(EVERYDAY)
        diagnostic = unit_info(DIAGNOSTIC)
        if (row.get('ActiveState') in ACTIVE or _job_pending(row) or _other_active()
                or diagnostic.get('ActiveState') in ACTIVE or _job_pending(diagnostic)):
            lifecycle['restore'] = 'deferred: another managed worker is active'
            return
        _validate_unit(EVERYDAY, row)
        if row.get('UnitFileState') != 'enabled' or not _f5_idle():
            lifecycle['restore'] = 'deferred: everyday disabled or F5 busy'
            return
        # Never trust a smaller/custom admission while restoring the default.
        settings = _private_json(Path.home() / '.config/mseries-ai/profiles.json')
        if _digest(Path.home() / '.config/mseries-ai/profiles.json') != lifecycle.get('prior_profiles_sha256'):
            lifecycle['restore'] = 'deferred: assistant settings changed during diagnosis'
            return
        profile = settings.get('profiles', {}).get('everyday', {})
        if profile.get('engine') != 'mlx' or profile.get('model') != 'qwen3.5-4b-mseries-4bit':
            lifecycle['restore'] = 'deferred: everyday profile identity changed'
            return
        reasons = quiet_reasons(int(max(6.5, profile.get('admission_gib', 6.5)) * GIB), admission=True)
        if reasons:
            lifecycle['restore'] = 'deferred: ' + '; '.join(reasons)
            return
        _run('start', EVERYDAY)
        lifecycle['restore'] = 'started previously enabled everyday 4B'
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        lifecycle['restore'] = 'deferred: ' + str(error)[:160]


def _invocation(row):
    value = row.get('InvocationID', '')
    if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
        raise Deferred('Managed worker invocation identity is unavailable')
    return value


def _job_pending(row):
    return row.get('Job', '') not in ('', '0', '0 /', '[]')


def _stop_owned(unit, identity, invocation, *, before_signal=lambda: None):
    """Signal a verified Linux pidfd; a replaced unit/PID never receives stop."""
    row = unit_info(unit)
    if row.get('ActiveState') not in ACTIVE:
        return False
    if (_invocation(row) != invocation or row.get('MainPID') != identity[0]
            or _validate_unit(unit, row, running=True) != identity or row.get('Restart') != 'no'):
        raise Deferred('Owned worker invocation/process changed; no signal was sent')
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise Deferred('Safe exact-process cancellation requires Linux pidfd support')
    process_fd = os.pidfd_open(identity[0], 0)
    try:
        # Opening a recycled PID produces a different descriptor. Verify again
        # while holding it; signalling this descriptor cannot hit a later PID.
        current = unit_info(unit)
        if (_invocation(current) != invocation or current.get('MainPID') != identity[0]
                or _validate_unit(unit, current, running=True) != identity):
            raise Deferred('Owned worker changed before its process descriptor was signalled')
        before_signal()  # Durable lifecycle intent precedes an interruptible send.
        signal.pidfd_send_signal(process_fd, signal.SIGTERM)
        if not select.select([process_fd], [], [], 45)[0]:
            raise Deferred('Owned worker did not exit within its cancellation bound')
        return True
    finally:
        os.close(process_fd)


def _capture_start(prior_invocation, lifecycle):
    row = unit_info(DIAGNOSTIC)
    if row.get('ActiveState') not in ACTIVE:
        return None
    invocation = _invocation(row)
    if invocation == prior_invocation:
        raise Deferred('Diagnostic start did not establish a fresh invocation')
    if not lifecycle.get('start_request_accepted'):
        raise Deferred('Interrupted start has ambiguous attribution; diagnostic is retained for recovery')
    accepted = lifecycle.get('diagnostic_invocation')
    if accepted is not None and invocation != accepted:
        raise Deferred('Diagnostic invocation changed after the accepted start')
    # Capture the invocation BEFORE any cmdline/proc validation can fail.
    lifecycle['diagnostic_invocation'] = invocation
    if not row.get('MainPID'):
        return None
    identity = _validate_unit(DIAGNOSTIC, row, running=True)
    lifecycle.update(diagnostic_started=True, diagnostic_pid=identity[0], diagnostic_starttime=identity[1])
    return identity


def _save_recovery(directory, lifecycle):
    """Keep ambiguous lifecycle metadata private; never publish command lines."""
    target = directory / ('runtime-recovery-' + uuid.uuid4().hex + '.json')
    fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as stream:
        json.dump({'schema_version': 'mseries.diagnostic.runtime-recovery.v1',
                   'lifecycle': lifecycle}, stream, sort_keys=True)
        stream.write('\n')
    lifecycle['recovery_file'] = str(target)


@contextmanager
def session(exclusive=False, require_qualification=True):
    """Yield owned lifecycle metadata; ambiguous mutations defer without guesses.

    The shared lock serializes our analysis clients, not a user's independent
    systemctl commands. Changed invocations are retained and never stopped.
    """
    if not OWNED_START_READY:
        raise Deferred('Experimental diagnostic runtime is off: independent start attribution is not implemented')
    config = read_config()
    if require_qualification:
        require_qualified()
    directory = Path.home() / '.local/state/mseries-troubleshooter'
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
        raise Deferred('Diagnostic lifecycle directory must be private and owned')
    fd = os.open(directory / 'analysis.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    lifecycle = {'endpoint': ENDPOINT, 'model_revision': MODEL_REVISION, 'exclusive': bool(exclusive),
                 'qualification_required': bool(require_qualification), 'idle_race_limitation': RACE_LIMITATION,
                 'diagnostic_started': False, 'diagnostic_stop': 'not started', 'restore': 'not requested'}
    identity = None
    prior_invocation = None
    start_attempted = False
    settled = True
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise Deferred('Another local analysis is active') from error
        if _other_active():
            raise Deferred('Another selected assistant profile owns the model budget')
        diag = unit_info(DIAGNOSTIC)
        _validate_unit(DIAGNOSTIC, diag)
        if diag.get('ActiveState') in ACTIVE or _job_pending(diag):
            raise Deferred('A diagnostic worker/job already exists; it will not be borrowed or stopped')
        prior_invocation = diag.get('InvocationID', '')
        everyday = unit_info(EVERYDAY)
        if everyday.get('ActiveState') in ACTIVE:
            if not exclusive:
                raise Deferred('Everyday assistant is active; explicit exclusive diagnosis is required')
            if everyday.get('UnitFileState') != 'enabled':
                raise Deferred('Everyday service is not the enabled default; it will not be stopped')
            everyday_identity = _validate_unit(EVERYDAY, everyday, running=True)
            everyday_invocation = _invocation(everyday)
            settings = _private_json(Path.home() / '.config/mseries-ai/profiles.json')
            lifecycle['prior_profiles_sha256'] = _digest(Path.home() / '.config/mseries-ai/profiles.json')
            lifecycle['prior_everyday_pid'] = everyday_identity[0]
            lifecycle['prior_everyday_invocation'] = everyday_invocation
            profile = settings.get('profiles', {}).get('everyday', {})
            if profile.get('engine') != 'mlx' or profile.get('model') != 'qwen3.5-4b-mseries-4bit':
                raise Deferred('Everyday profile is not the owned 4B default')
            _idle_checks(everyday_identity)
            def releasing():
                lifecycle['everyday_release_attempted'] = True
            stopped = _stop_owned(EVERYDAY, everyday_identity, everyday_invocation, before_signal=releasing)
            if not stopped or unit_info(EVERYDAY).get('ActiveState') in ACTIVE:
                raise Deferred('Everyday worker did not stop cleanly')
            lifecycle['everyday_released'] = True
        extra = int(config['profiles']['diagnostic']['admission_gib'] * GIB)
        for number in range(3):
            reasons = quiet_reasons(extra, admission=True)
            if reasons or not _f5_idle() or _other_active():
                raise Deferred('; '.join(reasons or ['F5 or another managed worker is active']))
            if number < 2:
                time.sleep(.25)
        _port_free()
        # Nonblocking start avoids waiting for readiness inside the mutation.
        # Record acceptance with termination signals deferred across this tiny
        # transaction; CLI/transport failures remain explicitly ambiguous.
        start_attempted, settled = True, False
        previous_mask = signal.pthread_sigmask(signal.SIG_BLOCK, {signal.SIGINT, signal.SIGTERM})
        try:
            _run('start', '--no-block', DIAGNOSTIC)
            lifecycle['start_request_accepted'] = True
        finally:
            signal.pthread_sigmask(signal.SIG_SETMASK, previous_mask)
        for attempt in range(120):
            if identity is None:
                identity = _capture_start(prior_invocation, lifecycle)
            if identity is not None:
                row = unit_info(DIAGNOSTIC)
                if (_invocation(row) != lifecycle['diagnostic_invocation']
                        or not _same_process(DIAGNOSTIC, identity)):
                    raise Deferred('Diagnostic worker stopped or changed before readiness')
                try:
                    lifecycle['model_id'] = verify_model()
                    break
                except (OSError, ValueError):
                    pass
            if attempt == 119:
                raise Deferred('Diagnostic model did not become ready within its bound')
            time.sleep(1)
        yield lifecycle
    finally:
        try:
            if start_attempted:
                try:
                    if identity is None:
                        identity = _capture_start(prior_invocation, lifecycle)
                    if identity is not None:
                        stopped = _stop_owned(DIAGNOSTIC, identity, lifecycle['diagnostic_invocation'])
                        lifecycle['diagnostic_stop'] = ('stopped exact owned process' if stopped
                            else 'already stopped or identity changed; no stop sent')
                    row = unit_info(DIAGNOSTIC)
                    settled = row.get('ActiveState') not in ACTIVE and not _job_pending(row)
                    if not settled:
                        lifecycle['diagnostic_stop'] = 'deferred: active or pending invocation requires recovery'
                except (Exception, KeyboardInterrupt) as error:
                    lifecycle['diagnostic_stop'] = 'deferred: ' + str(error)[:160]
                    settled = False
            if lifecycle.get('everyday_release_attempted'):
                if settled:
                    _restore_everyday(lifecycle)
                else:
                    lifecycle['restore'] = 'deferred: diagnostic start/stop attribution is unsettled'
            if not settled or (lifecycle.get('everyday_release_attempted') and not lifecycle['restore'].startswith('started')):
                try:
                    _save_recovery(directory, lifecycle)
                except (OSError, ValueError) as error:
                    lifecycle['recovery_error'] = type(error).__name__
        finally:
            os.close(fd)
