#!/usr/bin/python3
"""Prepare a pinned SER8 gateway candidate, then apply only its reviewed digest.

Preparation is unprivileged. Apply needs sudo and Python isolated mode. Existing
file imports are captured by identity and expanded for validation, while the
installed configuration retains its existing import/update behavior. Raw config and logs stay in private files.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import stat
import subprocess
import sys
import tempfile

CONFIG = Path('/etc/caddy/Caddyfile')
IMPORTS = {Path('/etc/cockpit-incus/access-log.caddy'), Path('/etc/cockpit-incus/projects-routes.caddy')}
CADDY = '/usr/bin/caddy'
UPSTREAM = 'techmore-2.tailf80972.ts.net'
LIMIT = 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def identity(info):
    return {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')}


def capture(path, owner, expected=None):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    with os.fdopen(fd, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_uid != owner or before.st_nlink != 1 or before.st_mode & 0o022 or before.st_size > LIMIT:
            raise ValueError('Unsafe file: ' + str(path))
        data = stream.read(LIMIT + 1)
        if len(data) > LIMIT or identity(before) != identity(os.fstat(stream.fileno())):
            raise ValueError('File changed while reading')
    if expected and digest(data) != expected:
        raise ValueError('Reviewed digest changed: ' + str(path))
    return data, identity(before)


def construct(base, dependencies, prefix, expand=False):
    if not re.fullmatch('[a-f0-9]{48}', prefix):
        raise ValueError('Invalid random route prefix')
    text = base.decode('utf-8')
    if re.search(r'(?i)(?<![\w.-])mdm\.stoverparc\.org(?![\w.-])', text) or '*.stoverparc.org' in text.lower():
        raise ValueError('Existing mdm/wildcard site needs a separate route review')
    if '{$' in text:
        raise ValueError('Environment substitutions require a separate review')
    # Only these two reviewed file imports may be expanded. Named snippets stay.
    used = set()
    output = []
    for line in text.splitlines(keepends=True):
        match = re.fullmatch(r'[ \t]*import[ \t]+([^\s#]+)[ \t]*(?:#[^\n]*)?\n?', line)
        if match:
            token = match[1]
            if token.startswith('/'):
                path = Path(token)
                if path not in IMPORTS or path not in dependencies:
                    raise ValueError('Unreviewed import: ' + token)
                body = dependencies[path].decode('utf-8')
                if '{$' in body or re.search(r'(?m)^\s*import\b', body):
                    raise ValueError('Nested/dynamic import requires a separate review')
                output.append('# Expanded reviewed import: ' + token + '\n' + body + '\n' if expand else line)
                used.add(path)
                continue
            if not re.fullmatch('[A-Za-z][A-Za-z0-9_]*', token):
                raise ValueError('Unreviewed import expression')
        elif re.search(r'\bimport\b', line.split('#', 1)[0]):
            raise ValueError('Ambiguous import syntax')
        output.append(line)
    if used != set(dependencies):
        raise ValueError('Import set differs from the reviewed dependency set')
    site = f'''
mdm.stoverparc.org {{
    bind 192.168.3.251
    handle_path /{prefix}/* {{
        reverse_proxy 127.0.0.1:18789
    }}
    handle {{
        reverse_proxy https://{UPSTREAM}:9443 {{
            header_up Host {{http.request.host}}
            transport http {{
                tls_server_name {UPSTREAM}
            }}
        }}
    }}
}}
'''
    # Preserve admin off. Activation requires a single controlled restart.
    return ''.join(output).encode() + site.encode()


def sync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def private_write(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out:
        out.write(data)
        out.flush()
        os.fsync(out.fileno())
    sync_directory(path.parent)


def run(command, directory, phase, timeout=45):
    with open(directory / (phase + '.log'), 'xb') as log:
        os.chmod(log.name, 0o600)
        process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                   env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin'}, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # runuser may have a Caddy child: stop the entire private validation
            # group, never the separately supervised production Caddy service.
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise RuntimeError(phase + ' timed out; private command group stopped')
    if code:
        raise RuntimeError(phase + ' failed; see private log')


def prepare(output):
    if os.geteuid() == 0:
        raise ValueError('Prepare as the normal operator')
    os.umask(0o077)
    output.mkdir(mode=0o700, parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix='gateway-', dir=output))
    base, meta = capture(CONFIG, 0)
    dependencies, entries = {}, []
    for i, path in enumerate(sorted(IMPORTS)):
        data, info = capture(path, 0)
        name = f'import-{i}.caddy'
        private_write(stage / name, data)
        dependencies[path] = data
        entries.append({'path': str(path), 'capture': name, 'sha256': digest(data), 'identity': info})
    prefix = secrets.token_hex(24)
    candidate = construct(base, dependencies, prefix)
    private_write(stage / 'base.Caddyfile', base)
    private_write(stage / 'candidate.Caddyfile', candidate)
    validation = construct(base, dependencies, prefix, expand=True)
    private_write(stage / 'validated.Caddyfile', validation)
    run([CADDY, 'adapt', '--config', str(stage / 'validated.Caddyfile'), '--adapter', 'caddyfile'], stage, 'adapt')
    request = {'schema': 1, 'operator_uid': os.getuid(), 'prefix': prefix, 'base_sha256': digest(base),
               'base_identity': meta, 'candidate_sha256': digest(candidate), 'validation_sha256': digest(validation), 'imports': entries}
    raw = (json.dumps(request, indent=2) + '\n').encode()
    private_write(stage / 'request.json', raw)
    environment = f'''HOST=127.0.0.1
PORT=8789
MSERIES_WEBRTC_ORIGINS=http://localhost:8789,http://127.0.0.1:8789,https://mdm.stoverparc.org
MSERIES_WEBRTC_PUBLIC_URL=https://mdm.stoverparc.org/{prefix}/
STUN_URL=stun:stun.cloudflare.com:3478
'''
    private_write(stage / 'desktop.environment', environment.encode())
    return {'stage': str(stage), 'request_sha256': digest(raw), 'candidate_sha256': digest(candidate), 'applied': False}


def check_service(active=True):
    result = subprocess.run(['/usr/bin/systemctl', 'show', 'caddy.service', '-p', 'ExecStart', '--value'],
                            capture_output=True, env={'PATH': '/usr/bin:/bin'}, timeout=5, check=True)
    matches = re.findall(r'argv\[\]=([^;]+)', result.stdout.decode())
    if len(matches) != 1 or shlex.split(matches[0]) != [CADDY, 'run', '--environ', '--config', str(CONFIG)]:
        raise ValueError('Caddy service no longer starts the reviewed configuration')
    if active:
        subprocess.run(['/usr/bin/systemctl', 'is-active', '--quiet', 'caddy.service'], check=True, timeout=5)


def transaction(config, base, candidate, metadata, recovery, runner=run, validation=None, check_dependencies=lambda: None):
    """After preflight, replace atomically; never overwrite a concurrent edit."""
    def unchanged(expected, expected_meta=None):
        data, info = capture(config, metadata['st_uid'])
        if data != expected or (expected_meta is not None and info != expected_meta):
            raise ValueError('Live Caddy configuration changed; prepare again')
        return info
    unchanged(base, metadata)
    check_dependencies()
    private_write(recovery / 'original.Caddyfile', base)
    def stage(data):
        fd, name = tempfile.mkstemp(prefix='.mseries-webrtc-', dir=config.parent)
        try:
            os.fchown(fd, metadata['st_uid'], metadata['st_gid'])
            os.fchmod(fd, stat.S_IMODE(metadata['st_mode']))
            with os.fdopen(fd, 'wb') as stream:
                fd = -1
                stream.write(data); stream.flush(); os.fsync(stream.fileno())
        except BaseException:
            if fd >= 0:
                os.close(fd)
            os.unlink(name)
            raise
        return Path(name)
    staged = stage(candidate)
    validation_stage = stage(validation if validation is not None else candidate)
    committed = False
    installed = None
    try:
        runner(['/usr/sbin/runuser', '-u', 'caddy', '--', CADDY, 'validate', '--config', str(validation_stage), '--adapter', 'caddyfile'], recovery, 'validate')
        unchanged(base, metadata)
        check_dependencies()
        if staged.read_bytes() != candidate:
            raise ValueError('Validated candidate changed')
        os.replace(staged, config); committed = True
        directory = os.open(config.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
        installed = unchanged(candidate)
        runner(['/usr/bin/systemctl', 'restart', 'caddy.service'], recovery, 'restart')
        runner(['/usr/bin/systemctl', 'is-active', '--quiet', 'caddy.service'], recovery, 'active')
        unchanged(candidate, installed)
        check_dependencies()
        return {'state': 'restarted', 'recovery': str(recovery), 'public_tls_verified': False}
    except Exception:
        if committed:
            # Preserve an administrator edit made since our replacement.
            if installed is None:
                raise RuntimeError('Installed configuration identity is unconfirmed; manual recovery required')
            unchanged(candidate, installed)
            original = stage(base)
            os.replace(original, config)
            sync_directory(config.parent)
            runner(['/usr/bin/systemctl', 'restart', 'caddy.service'], recovery, 'rollback')
            runner(['/usr/bin/systemctl', 'is-active', '--quiet', 'caddy.service'], recovery, 'rollback-active')
            unchanged(base)
        raise
    finally:
        for path in (staged, validation_stage):
            if path.exists():
                path.unlink()


def apply(stage, request_sha):
    if not sys.flags.isolated or os.geteuid() != 0 or not os.environ.get('SUDO_UID', '').isdecimal() or int(os.environ['SUDO_UID']) == 0:
        raise ValueError('Apply requires sudo /usr/bin/python3 -I and the normal operator identity')
    owner = int(os.environ['SUDO_UID'])
    raw, _ = capture(stage / 'request.json', owner, request_sha)
    request = json.loads(raw)
    if request.get('schema') != 1 or request.get('operator_uid') != owner:
        raise ValueError('Request operator mismatch')
    base, _ = capture(stage / 'base.Caddyfile', owner, request['base_sha256'])
    candidate, _ = capture(stage / 'candidate.Caddyfile', owner, request['candidate_sha256'])
    dependencies = {}
    validation, _ = capture(stage / 'validated.Caddyfile', owner, request['validation_sha256'])
    if len(request['imports']) != len(IMPORTS):
        raise ValueError('Unexpected import count')
    for entry in request['imports']:
        path = Path(entry['path'])
        if path not in IMPORTS or path in dependencies or not re.fullmatch(r'import-[01]\.caddy', entry['capture']):
            raise ValueError('Unexpected import')
        data, _ = capture(stage / entry['capture'], owner, entry['sha256'])
        live, info = capture(path, 0, entry['sha256'])
        if data != live or info != entry['identity']:
            raise ValueError('Imported configuration changed; prepare again')
        dependencies[path] = data
    live, info = capture(CONFIG, 0, request['base_sha256'])
    if live != base or info != request['base_identity'] or candidate != construct(base, dependencies, request['prefix']) or validation != construct(base, dependencies, request['prefix'], expand=True):
        raise ValueError('Reviewed construction or base identity changed')
    # Check immutable parent ownership before privileged writes/stages.
    for path in [CONFIG.parent, Path('/usr/bin'), Path('/var/lib')]:
        meta = path.lstat()
        if not stat.S_ISDIR(meta.st_mode) or meta.st_uid != 0 or meta.st_mode & 0o022:
            raise ValueError('Unsafe privileged parent')
    binary = Path(CADDY).lstat()
    if not stat.S_ISREG(binary.st_mode) or binary.st_uid != 0 or binary.st_mode & 0o022:
        raise ValueError('Unsafe Caddy executable')
    check_service()
    recovery_root = Path('/var/lib/mseries-webrtc-gateway')
    recovery_root.mkdir(mode=0o700, exist_ok=True)
    info_root = recovery_root.lstat()
    if not stat.S_ISDIR(info_root.st_mode) or info_root.st_uid != 0 or info_root.st_mode & 0o077:
        raise ValueError('Unsafe recovery directory')
    lock_fd = os.open(recovery_root / 'apply.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        sync_directory(recovery_root.parent)
        recovery = Path(tempfile.mkdtemp(prefix='apply-', dir=recovery_root))
        sync_directory(recovery_root)
        def check_dependencies():
            for entry in request['imports']:
                _, meta = capture(Path(entry['path']), 0, entry['sha256'])
                if meta != entry['identity']:
                    raise ValueError('Imported configuration identity changed')
        def execute(command, directory, phase):
            if phase in ('restart', 'rollback'):
                check_service(active=False)
            run(command, directory, phase)
        try:
            result = transaction(CONFIG, base, candidate, request['base_identity'], recovery, runner=execute, validation=validation, check_dependencies=check_dependencies)
        except Exception as error:
            result = {'state': 'activation_failed', 'recovery': str(recovery), 'error': str(error)[:300],
                      'current_config_sha256': digest(CONFIG.read_bytes()),
                      'rollback_config_restored': CONFIG.read_bytes() == base}
            private_write(recovery / 'result.json', (json.dumps(result) + '\n').encode())
            raise RuntimeError('Activation failed; inspect ' + str(recovery / 'result.json')) from error
        private_write(recovery / 'result.json', (json.dumps(result) + '\n').encode())
        return result
    finally:
        os.close(lock_fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('--output', type=Path, required=True)
    p = sub.add_parser('apply'); p.add_argument('--stage', type=Path, required=True); p.add_argument('--request-sha256', required=True)
    args = parser.parse_args()
    try:
        result = prepare(args.output) if args.command == 'prepare' else apply(args.stage, args.request_sha256)
        print(json.dumps(result)); return 0
    except Exception as error:
        print(json.dumps({'state': 'not_confirmed', 'error': str(error)[:300]})); return 1


if __name__ == '__main__':
    sys.exit(main())
