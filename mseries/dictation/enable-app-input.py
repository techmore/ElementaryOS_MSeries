#!/usr/bin/python3
"""Prepare ChatGPT's next full launch for strict focus-bound dictation.

Only a per-user desktop entry is changed. Never launches, stops, inspects the
contents of, or changes preferences inside the running application.
"""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).resolve().parent
HOME = Path.home()
BASE = HOME / '.local/share/mseries/stream'
USER_ENTRY = HOME / '.local/share/applications/chatgpt.desktop'
SYSTEM_ENTRY = Path('/usr/share/applications/chatgpt.desktop')
STATE = HOME / '.local/state/mseries-app-input/chatgpt-v1'
KNOWN_COMMANDS = {'chatgpt', '/usr/bin/chatgpt', '/usr/lib/chatgpt/codex-launcher', '/usr/lib/chatgpt/ChatGPT'}
MAX_ENTRY_BYTES = 256 * 1024


def manager():
    source = HERE.parent / 'install-dictation-input.py'
    if not source.is_file():
        source = BASE / 'dictation-manage.py'
    if not source.is_file():
        raise ValueError('The reviewed dictation payload manager is unavailable')
    spec = importlib.util.spec_from_file_location('app_input_payload', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_entry(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_ENTRY_BYTES:
        raise ValueError('Desktop entry is absent, oversized or a symlink; it was preserved')
    raw = path.read_bytes()
    if len(raw) > MAX_ENTRY_BYTES:
        raise ValueError('Desktop entry exceeded its bound; it was preserved')
    raw.decode('utf-8')
    return raw


def desktop_argument(value):
    """Quote a literal Exec argument through both desktop-entry escape layers."""
    value = str(value)
    if any(char in value for char in '\0\r\n'):
        raise ValueError('Unsupported control character in launcher path')
    result = []
    for char in value:
        if char == '%':
            result.append('%%')
        elif char == '\\':
            result.append('\\' * 4)
        elif char in '"$`':
            result.append('\\' * 2 + char)
        else:
            result.append(char)
    return '"' + ''.join(result) + '"'


def prefix():
    return ' '.join(desktop_argument(value) for value in
                    ('/usr/bin/python3', BASE / 'dictation-launch.py', '--chromium')) + ' '


def first_command(value):
    """Recognize only a simple known executable; retain its argument tail exactly.

    Desktop Exec is not a shell command. In particular, never round-trip its
    argument/field-code tail through shell splitting or shell quoting.
    """
    value = value.lstrip(' \t')
    if not value:
        raise ValueError('Empty ChatGPT Exec entry was preserved')
    if value.startswith('"'):
        end = value.find('"', 1)
        if end < 0 or '\\' in value[1:end] or (end + 1 < len(value) and value[end + 1] not in ' \t'):
            raise ValueError('Custom ChatGPT launcher quoting was preserved')
        executable, tail = value[1:end], value[end + 1:]
    else:
        end = next((index for index, char in enumerate(value) if char in ' \t'), len(value))
        executable, tail = value[:end], value[end:]
    if executable not in KNOWN_COMMANDS:
        raise ValueError('Custom ChatGPT launcher was preserved; only the known packaged executable is supported')
    return executable, tail


def rewrite(data):
    text = data.decode('utf-8')
    lines = []
    group = None
    groups, keys = set(), set()
    main_exec = False
    for line in text.splitlines(keepends=True):
        ending = '\r\n' if line.endswith('\r\n') else '\n' if line.endswith('\n') else ''
        body = line[:-len(ending)] if ending else line
        stripped = body.strip(' \t')
        if not stripped or stripped.startswith('#'):
            lines.append(line)
            continue
        if stripped.startswith('[') and stripped.endswith(']'):
            group = stripped[1:-1]
            if not group or group in groups:
                raise ValueError('Ambiguous desktop entry group was preserved')
            groups.add(group)
            lines.append(line)
            continue
        key_part, separator, raw_value = body.partition('=')
        key = key_part.strip(' \t')
        if not separator or not key or group is None or any(ord(char) < 32 for char in key):
            raise ValueError('Unsupported desktop entry format was preserved')
        identity = (group, key)
        if identity in keys or key.startswith(('Exec[', 'DBusActivatable[')):
            raise ValueError('Duplicate or localized launcher control key was preserved')
        keys.add(identity)
        if key == 'DBusActivatable':
            # Boolean control keys are not localized. Only explicit false is
            # safe; unknown spellings must not make activation bypass Exec.
            if raw_value.strip(' \t') != 'false':
                raise ValueError('D-Bus activated or ambiguous launcher was preserved because Exec flags may be ignored')
        if key == 'Exec':
            if group != 'Desktop Entry' and not group.startswith('Desktop Action '):
                raise ValueError('Custom desktop Exec group was preserved')
            leading = raw_value[:len(raw_value) - len(raw_value.lstrip(' \t'))]
            value = raw_value[len(leading):]
            managed = value.startswith(prefix())
            original = value[len(prefix()):] if managed else value
            executable, tail = first_command(original)
            line = key_part + '=' + leading + prefix() + desktop_argument(executable) + tail + ending
            if group == 'Desktop Entry':
                main_exec = True
        lines.append(line)
    if not main_exec:
        raise ValueError('No known main ChatGPT Exec entry was found; desktop entry was preserved')
    return ''.join(lines).encode('utf-8')


def source_entry():
    return USER_ENTRY if USER_ENTRY.exists() or USER_ENTRY.is_symlink() else SYSTEM_ENTRY


def _validate_target_scope(payload):
    if set(payload.data['files']) - {str(USER_ENTRY)}:
        raise ValueError('Private app-input checkpoint has an unexpected target; no file changed')


def check(payload):
    _validate_target_scope(payload)
    raw = read_entry(USER_ENTRY) if USER_ENTRY.exists() or USER_ENTRY.is_symlink() else None
    row = payload.data['files'].get(str(USER_ENTRY), {})
    actual = digest(raw) if raw is not None else None
    expected = row.get('installed_sha256')
    mode_matches = raw is not None and stat.S_IMODE(USER_ENTRY.stat().st_mode) == 0o644
    prepared = bool(expected and actual == expected and mode_matches)
    return {'app': 'chatgpt', 'override_exists': raw is not None,
            'override_sha256': actual, 'staged': prepared,
            'owner_changed': bool(expected and (actual != expected or not mode_matches)),
            'private_backup_retained': payload.path.is_file(),
            'next_launch_flags': ['--force-renderer-accessibility'] if prepared else [],
            'next_launch_input_environment': ['GTK_IM_MODULE=ibus', 'QT_IM_MODULE=ibus', 'XMODIFIERS=@im=ibus'] if prepared else [],
            'running_app_compatibility': 'not checked',
            'activation': 'requires an owner-controlled full app quit and launch' if prepared else 'not staged'}


def stage(payload):
    _validate_target_scope(payload)
    if check(payload)['owner_changed']:
        raise ValueError('Owner changed the managed launcher; it was preserved')
    if not (BASE / 'dictation-launch.py').is_file():
        raise ValueError('Install the reviewed dictation launcher before preparing app input')
    source = source_entry()
    raw = read_entry(source)
    candidate = rewrite(raw)  # Reject every unknown action before writing anything.
    if not payload.data['metadata']:
        payload.data['metadata'] = {'app': 'chatgpt', 'source': 'user' if source == USER_ENTRY else 'system',
                                    'source_sha256': digest(raw), 'activation': 'next full owner-controlled launch'}
    payload.install(USER_ENTRY, candidate, 0o644)
    return check(payload)


def rollback(payload):
    _validate_target_scope(payload)
    if not payload.data['files'].get(str(USER_ENTRY), {}).get('installed_sha256'):
        raise ValueError('No active app-input checkpoint exists')
    if check(payload)['owner_changed']:
        raise ValueError('Owner changed the managed launcher; rollback preserved it')
    payload.restore()  # Validates current owner bytes and private backup first.


@contextlib.contextmanager
def transaction():
    if STATE.is_symlink() or (STATE / 'baseline.json').is_symlink():
        raise ValueError('Private app-input state is a symlink; no file changed')
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    if STATE.stat().st_uid != os.getuid():
        raise ValueError('Private app-input state belongs to another user')
    STATE.chmod(0o700)
    fd = os.open(STATE / '.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    finally:
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--app', choices=('chatgpt',), required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument('--stage', action='store_true')
    action.add_argument('--rollback', action='store_true')
    action.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise SystemExit('Run as the desktop user')
    if STATE.is_symlink() or (STATE / 'baseline.json').is_symlink():
        raise ValueError('Private app-input state is a symlink; no file changed')
    payload_type = manager().Payload
    if args.check:
        print(json.dumps(check(payload_type(STATE)), indent=2))
    else:
        # Read the baseline only after taking the lock, so concurrent stages
        # cannot replace the first pre-upgrade owner baseline with a stale copy.
        with transaction():
            payload = payload_type(STATE)
            if args.stage:
                print(json.dumps(stage(payload), indent=2))
            else:
                rollback(payload)
                print('Previous per-user ChatGPT launcher restored. The running app was untouched.')


if __name__ == '__main__':
    main()
