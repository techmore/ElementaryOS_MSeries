#!/usr/bin/python3
"""Stage, activate or roll back the focus-bound Unicode F5 output path."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'dictation' if (HERE / 'dictation').is_dir() else HERE
HOME = Path.home()
BASE = HOME / '.local/share/mseries/stream'
UNITS = HOME / '.config/systemd/user'
STATE = HOME / '.local/state/mseries-dictation-input'
ENGINE = 'mseries-dictation'
SERVICE = 'mseries-stream-dictate.service'
INPUT_SERVICE = 'mseries-dictation-input.service'
DROPIN = UNITS / (SERVICE + '.d') / '40-universal-input.conf'
ENVIRONMENT = HOME / '.config/environment.d/60-mseries-dictation.conf'
BRAVE_DESKTOP = HOME / '.local/share/applications/brave-browser.desktop'
PANEL_DESKTOP = HOME / '.local/share/applications/org.techmore.Dictation.desktop'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def atomic(path, data, mode):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name + '-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            os.fchmod(stream.fileno(), mode)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name): os.unlink(name)


class Payload:
    """Keep the first baseline; refuse rollback over subsequent owner edits."""
    def __init__(self, directory):
        self.directory = directory
        self.path = directory / 'baseline.json'
        self.data = json.loads(self.path.read_text()) if self.path.exists() else {'files': {}, 'metadata': {}}

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        atomic(self.path, (json.dumps(self.data, indent=2) + '\n').encode(), 0o600)

    def remember(self, path):
        key = str(path)
        if key in self.data['files']: return
        if path.is_symlink(): raise ValueError('Refusing managed symlink: ' + key)
        row = {'existed': path.exists()}
        if path.exists():
            raw = path.read_bytes()
            backup = digest(key.encode()) + '.backup'
            self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            atomic(self.directory / backup, raw, 0o600)
            row.update(backup=backup, sha256=digest(raw), mode=stat.S_IMODE(path.stat().st_mode))
        self.data['files'][key] = row
        self.save()

    def install(self, path, data, mode):
        self.remember(path)
        row = self.data['files'][str(path)]
        if row.get('installed_sha256'):
            if path.is_symlink() or not path.exists() or digest(path.read_bytes()) != row['installed_sha256']:
                raise ValueError('Owner changed managed file; reconcile first: ' + str(path))
        elif (path.exists() != row['existed'] or (path.exists() and digest(path.read_bytes()) != row['sha256'])):
            raise ValueError('Owner changed baseline file; reconcile first: ' + str(path))
        atomic(path, data, mode)
        row['installed_sha256'] = digest(data)
        self.save()

    def validate_restore(self):
        for name, row in self.data['files'].items():
            path = Path(name)
            if row.get('installed_sha256'):
                if path.is_symlink() or not path.exists() or digest(path.read_bytes()) != row['installed_sha256']:
                    raise ValueError('Owner changed managed file; rollback preserved it: ' + name)
            elif path.exists() != row['existed'] or (path.exists() and digest(path.read_bytes()) != row['sha256']):
                raise ValueError('Owner changed baseline file; rollback preserved it: ' + name)
            if row['existed'] and digest((self.directory / row['backup']).read_bytes()) != row['sha256']:
                raise ValueError('Backup digest differs: ' + name)

    def restore(self):
        self.validate_restore()  # Validate everything before changing any file.
        for name, row in self.data['files'].items():
            path = Path(name)
            if row['existed']:
                atomic(path, (self.directory / row['backup']).read_bytes(), row['mode'])
            elif path.exists():
                path.unlink()
            row.pop('installed_sha256', None)
        self.save()


def command(args, check=True):
    return subprocess.run(args, text=True, capture_output=True, check=check)


def systemctl(*args, check=True):
    return command(['systemctl', '--user', *args], check=check)


def enabled(unit):
    return systemctl('is-enabled', unit, check=False).returncode == 0


def brave_override(text):
    lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith('Exec='):
            executable, _, tail = line[5:].rstrip('\n').partition(' ')
            if Path(executable).name not in ('brave', 'brave-browser', 'brave-browser-stable'):
                raise ValueError('Custom browser launcher needs manual integration; it was preserved')
            if '--force-renderer-accessibility' not in line:
                line = 'Exec=' + executable + ' --force-renderer-accessibility' + (' ' + tail if tail else '') + '\n'
        lines.append(line)
    return ''.join(lines)


PREFERENCES = [('org.gnome.desktop.interface', 'toolkit-accessibility', 'true'),
               ('org.gnome.desktop.interface', 'gtk-im-module', "'ibus'")]


def remember_preferences(payload):
    metadata = payload.data['metadata']
    if 'preferences' not in metadata:
        metadata['preferences'] = [{'schema': schema, 'key': key, 'desired': value,
            'original': command(['gsettings', 'get', schema, key]).stdout.strip()}
            for schema, key, value in PREFERENCES]
        payload.save()


def active(unit):
    return systemctl('is-active', '--quiet', unit, check=False).returncode == 0


def check_idle_capture(proc_root=Path('/proc')):
    pid = int(systemctl('show', SERVICE, '-p', 'MainPID', '--value').stdout.strip() or '0')
    if not pid: return
    for children in (proc_root / str(pid) / 'task').glob('*/children'):
        for child in children.read_text().split():
            try: state = (proc_root / child / 'stat').read_text().rpartition(')')[2].split()[0]
            except (FileNotFoundError, IndexError): continue
            if state not in ('Z', 'X'):
                raise ValueError('F5 capture or output helper is active; release the key before switching')


def quiet_admission():
    candidates = [HERE / 'local-ai', BASE]
    import sys
    for path in candidates:
        if (path / 'machine.py').exists(): sys.path.insert(0, str(path)); break
    from machine import snapshot, violations, DEFAULT_POLICY
    settings = HOME / '.config/mseries-ai/profiles.json'
    policy = json.loads(settings.read_text())['policy'] if settings.exists() else DEFAULT_POLICY
    sample = snapshot()
    if (violations(sample, policy, 1024 ** 3) or max(sample['fans_rpm'].values(), default=9999) >= 2700
            or max(sample['temperatures_c'].values(), default=999) > 63):
        raise ValueError('Wait for cool admission before restarting the speech model')


def stage(payload):
    if not (BASE / 'venv/bin/python').exists() or not (BASE / 'stream-dictate.py').exists():
        raise ValueError('Install the pinned streaming F5 runtime first')
    command(['/usr/bin/python3', '-c', "import gi; gi.require_version('IBus','1.0'); gi.require_version('Atspi','2.0')"])
    if not payload.data['metadata']:
        prior = command(['ibus', 'engine']).stdout.strip()
        if not prior or prior == ENGINE: raise ValueError('Cannot establish the original input-method baseline')
        payload.data['metadata'] = {'engine': prior, 'stream_active': active(SERVICE),
            'input_active': active(INPUT_SERVICE), 'input_enabled': enabled(INPUT_SERVICE),
            'activation_started': False, 'activated': False}
        payload.save()
    remember_preferences(payload)
    for name in ['stream-dictate.py', 'dictation-input.py', 'dictation-input-client.py', 'dictation_status.py', 'dictation_resources.py', 'dictation_model.py', 'dictation_ane.py', 'ane-worker-shim.py', 'dictation_mlx.py', 'mlx-speech-worker.py', 'dictation_voice.py', 'voice-assistant.py', 'dictation-launch.py', 'dictation_review.py', 'dictation_pipeline.py', 'dictation_live.py', 'dictation-panel.py']:
        payload.install(BASE / name, (SOURCE / name).read_bytes(), 0o755)
    payload.install(BASE / 'dictation-manage.py', Path(__file__).read_bytes(), 0o755)
    machine = HERE / 'local-ai/machine.py' if (HERE / 'local-ai/machine.py').exists() else BASE / 'machine.py'
    payload.install(BASE / 'machine.py', machine.read_bytes(), 0o644)
    payload.install(UNITS / INPUT_SERVICE, (SOURCE / INPUT_SERVICE).read_bytes(), 0o644)
    payload.install(BASE / INPUT_SERVICE, (SOURCE / INPUT_SERVICE).read_bytes(), 0o644)
    payload.remember(DROPIN)
    payload.remember(ENVIRONMENT)
    payload.remember(PANEL_DESKTOP)


def install_panel(payload, speech_only=False):
    # Desktop Exec quoting, not shell quoting. Absolute arguments are passed
    # directly to Python; no shell or environment expansion is involved.
    def argument(value):
        return '"' + ''.join(('\\' + c) if c in '\\"`$' else c for c in str(value)) + '"'
    arguments = ['/usr/bin/python3', BASE / 'dictation-launch.py', '/usr/bin/python3', BASE / 'dictation-panel.py']
    if speech_only:
        arguments = ['/usr/bin/env', 'MSERIES_DICTATION_SPEECH_ONLY=1', *arguments]
    desktop = ('[Desktop Entry]\nType=Application\nName=Dictation\n' +
        ('Comment=Local English F5 speech\n' if speech_only else 'Comment=Local F5 speech and optional transcript review\n') +
        'Icon=audio-input-microphone\nExec=' + ' '.join(argument(value) for value in arguments) +
        '\nTerminal=false\nCategories=Utility;Accessibility;\nStartupNotify=true\n')
    payload.install(PANEL_DESKTOP, desktop.encode(), 0o644)


def rollback(payload):
    check_idle_capture()
    payload.validate_restore()
    baseline = payload.data['metadata']
    current = command(['ibus', 'engine'], check=False).stdout.strip()
    restore_engine = baseline['engine'] if current in (ENGINE, '', 'dummy') else current
    systemctl('stop', INPUT_SERVICE, check=False)
    time.sleep(.1)  # Let IBus remove the dynamic provider before restoring selection.
    after_stop = command(['ibus', 'engine'], check=False).stdout.strip()
    if after_stop in (ENGINE, '', 'dummy'):
        selector = BASE / 'dictation-input-client.py'
        if not selector.exists(): selector = SOURCE / 'dictation-input-client.py'
        command(['/usr/bin/python3', str(selector), 'select', restore_engine])
    if baseline['activation_started']:
        for preference in baseline.get('preferences', []):
            schema, key = preference['schema'], preference['key']
            if command(['gsettings', 'get', schema, key]).stdout.strip() == preference['desired']:
                command(['gsettings', 'set', schema, key, preference['original']])
    if not baseline['input_enabled']: systemctl('disable', INPUT_SERVICE, check=False)
    payload.restore()
    systemctl('daemon-reload')
    if baseline['activation_started'] and baseline['stream_active']:
        try: quiet_admission()
        except ValueError:
            print('Original files and input method restored; speech restart awaits cool admission. Its enabled state is preserved.')
        else: systemctl('restart', SERVICE)
    if baseline['input_active']: systemctl('start', INPUT_SERVICE)
    baseline.update(activation_started=False, activated=False)
    payload.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    for name in ['stage', 'activate', 'rollback', 'status', 'panel']: actions.add_argument('--' + name, action='store_true')
    args = parser.parse_args()
    if os.geteuid() == 0: raise SystemExit('Run as the desktop user')
    payload = Payload(STATE)
    if args.status:
        import importlib.util
        spec = importlib.util.spec_from_file_location('dictation_status_read', SOURCE / 'dictation_status.py')
        status_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(status_module)
        lifecycle = status_module.read_status()
        pid = int(systemctl('show', SERVICE, '-p', 'MainPID', '--value').stdout.strip() or '0')
        if lifecycle and lifecycle['pid'] != pid: lifecycle = None
        bridge_ready = active(INPUT_SERVICE) and command(['/usr/bin/python3', str(BASE / 'dictation-input-client.py'), 'ready'], check=False).returncode == 0
        print(json.dumps({'bridge_ready': bridge_ready, 'staged': any(r.get('installed_sha256') for r in payload.data['files'].values()),
            'backup_retained': payload.path.exists(), 'activated': payload.data['metadata'].get('activated', False), 'input_active': active(INPUT_SERVICE),
            'stream_active': active(SERVICE), 'engine': command(['ibus', 'engine'], check=False).stdout.strip(), 'lifecycle': lifecycle}, indent=2))
        return
    if args.rollback:
        if not payload.data['metadata']: raise ValueError('No saved installation to roll back')
        if payload.data['metadata'].get('activation_started'): quiet_admission()
        rollback(payload)
        print('Previous speech payload and input method restored; backup retained.')
        return
    if args.panel and not payload.data['metadata'].get('activated'):
        raise ValueError('Activate the qualified Unicode speech path before installing its review panel')
    check_idle_capture()
    if args.activate: quiet_admission()
    stage(payload)
    if args.panel:
        install_panel(payload)
        print('Dictation review panel installed; speech services unchanged.')
        return
    if not args.activate:
        print('Payload staged; running service unchanged. Use --activate after acceptance checks.')
        return
    try:
        install_panel(payload)
        payload.data['metadata']['activation_started'] = True
        payload.save()
        payload.install(DROPIN, b'[Unit]\nPartOf=graphical-session.target\nWants=mseries-dictation-input.service\nAfter=mseries-dictation-input.service\n\n[Service]\nEnvironment=STREAM_OUTPUT=ibus\nEnvironment=STREAM_BACKEND=cpu\n', 0o644)
        payload.install(ENVIRONMENT, b'GTK_IM_MODULE=ibus\nQT_IM_MODULE=ibus\nXMODIFIERS=@im=ibus\n', 0o644)
        for preference in payload.data['metadata']['preferences']:
            command(['gsettings', 'set', preference['schema'], preference['key'], preference['desired']])
        browser_source = BRAVE_DESKTOP if BRAVE_DESKTOP.exists() else Path('/usr/share/applications/brave-browser.desktop')
        if browser_source.exists() and not BRAVE_DESKTOP.is_symlink():
            try: browser_text = brave_override(browser_source.read_text())
            except ValueError as error: print(str(error))
            else: payload.install(BRAVE_DESKTOP, browser_text.encode(), 0o644)
        systemctl('daemon-reload')
        systemctl('enable', INPUT_SERVICE)
        previous_engine = command(['ibus', 'engine'], check=False).stdout.strip()
        if previous_engine in (ENGINE, '', 'dummy'): previous_engine = payload.data['metadata']['engine']
        systemctl('restart', INPUT_SERVICE)
        if command(['ibus', 'engine'], check=False).stdout.strip() in (ENGINE, '', 'dummy'):
            command(['/usr/bin/python3', str(BASE / 'dictation-input-client.py'), 'select', previous_engine])
        command(['/usr/bin/python3', str(BASE / 'dictation-input-client.py'), 'ready'])
        systemctl('restart', SERVICE)
        import importlib.util
        spec = importlib.util.spec_from_file_location('installed_dictation_status', BASE / 'dictation_status.py')
        status_module = importlib.util.module_from_spec(spec); spec.loader.exec_module(status_module)
        for _ in range(60):
            row = status_module.read_status()
            pid = int(systemctl('show', SERVICE, '-p', 'MainPID', '--value').stdout.strip() or '0')
            if row and row['pid'] == pid and row['phase'] == 'ready' and row['output'] == 'ibus' and row['backend'] == 'cpu': break
            if not active(SERVICE) or not active(INPUT_SERVICE): raise ValueError('Speech activation did not remain active')
            time.sleep(.5)
        else: raise ValueError('Speech model did not report ready with Unicode output')
        time.sleep(1)
        stable_pid = int(systemctl('show', SERVICE, '-p', 'MainPID', '--value').stdout.strip() or '0')
        command(['/usr/bin/python3', str(BASE / 'dictation-input-client.py'), 'ready'])
        if stable_pid != pid or not active(SERVICE) or not active(INPUT_SERVICE):
            raise ValueError('Speech service did not remain healthy after opening its keyboard')
    except Exception:
        rollback(payload)
        raise
    payload.data['metadata']['activated'] = True
    payload.save()
    print('Unicode F5 output activated. Rollback: python3 mseries/install-dictation-input.py --rollback')


if __name__ == '__main__':
    main()
