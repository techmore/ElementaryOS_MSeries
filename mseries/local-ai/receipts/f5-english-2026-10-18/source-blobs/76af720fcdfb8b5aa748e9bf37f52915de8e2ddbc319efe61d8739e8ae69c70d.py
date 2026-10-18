#!/usr/bin/python3
"""Actual installed-app dictation acceptance, using public audio on private buses.

Does not press a physical F5, record/play audio, send a chat, save a task, open an
owner window or load owner app settings/accounts. The controller file-input route
uses the same start/ASR/input/final-drain path as the keyboard listener.
"""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
import wave

HERE = Path(__file__).resolve().parent
APP = 'io.github.qwersyk.Newelle'
REFERENCE = ('He hoped there would be stew for dinner, turnips and carrots and bruised '
             'potatoes and fat mutton pieces to be ladled out in thick, peppered, '
             'flour-fattened sauce')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--app', choices=['code', 'newelle', 'tasks'], required=True)
parser.add_argument('--receipt-dir', type=Path, required=True)
parser.add_argument('--model', type=Path, required=True)
parser.add_argument('--wav', type=Path, default=Path.home()/'.local/share/mseries/stream/libri.wav')
parser.add_argument('--fixtures-only', action='store_true')
parser.add_argument('--software-wm', action='store_true', help='Run Gala only on this private Xvfb display, with software rendering and no shell apps')
parser.add_argument('--newelle-ui', action='store_true', help=argparse.SUPPRESS)
args = parser.parse_args()

if args.newelle_ui:
    # This branch runs under the installed Flatpak's own Python/runtime. All
    # mutable app paths, preferences and history are newly created synthetic state.
    import gettext
    import gi
    gettext.install('newelle', '/app/share/locale')
    sys.path.insert(0, '/app/share/newelle')
    from newelle.main import MyApp
    from gi.repository import Gio, GLib, Gdk
    settings = Gio.Settings.new(APP)
    for key in ['memory-on', 'tts-on', 'websearch-on', 'secondary-llm-on', 'auto-generate-name']:
        settings.set_boolean(key, False)
    settings.set_boolean('welcome-screen-shown', True)
    settings.set_string('language-model', 'openai')
    settings.set_string('llm-settings', json.dumps({'openai': {
        'endpoint': 'http://127.0.0.1:9/v1', 'api': 'synthetic-unused',
        'model': 'dictation-no-send'}}))
    settings.set_string('path', str(args.receipt_dir/'history'))
    settings.set_string('mcp-servers', '[]')
    Gio.Settings.sync()
    app = MyApp(application_id=APP, version='1.6.0')
    app.set_flags(app.get_flags() | Gio.ApplicationFlags.NON_UNIQUE)
    row = {'ready': False, 'text': '', 'preedit': []}
    view = None
    last_command = None
    def write():
        tmp = args.receipt_dir/'ui.tmp'
        tmp.write_text(json.dumps(row))
        os.replace(tmp, args.receipt_dir/'ui.json')
    def observe_preedit(widget, text):
        row['preedit'].append({'monotonic_s': time.monotonic(), 'text': text})
    def poll():
        global view, last_command
        if view is None:
            for window in app.get_windows():
                if not hasattr(window, 'chat_tabs'):
                    continue
                tab = window.get_active_chat_tab() if hasattr(window, 'get_active_chat_tab') else None
                if tab is not None:
                    view = tab.input_panel.get_input_panel()
                    view.connect('preedit-changed', observe_preedit)
                    window.present()
                    window.get_surface().focus(Gdk.CURRENT_TIME)
                    view.grab_focus()
                    row['ready'] = True
                    break
        if view is not None:
            command = args.receipt_dir/'ui-command.json'
            if command.exists():
                value = command.read_text()
                if value != last_command:
                    last_command = value
                    if json.loads(value)['action'] == 'clear':
                        view.get_buffer().set_text('')
                        view.grab_focus()
            buffer = view.get_buffer()
            row['text'] = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        write()
        return True
    GLib.timeout_add(50, poll)
    GLib.timeout_add_seconds(180, lambda: (app.quit(), False)[1])
    app.run(['f5-real-apps-private-newelle'])
    raise SystemExit(0)

if os.environ.get('MSERIES_REAL_APP_SESSION') != '1':
    with tempfile.TemporaryDirectory(prefix='mseries-real-app-') as scratch:
        result = subprocess.run(['dbus-run-session', '--', 'xvfb-run', '-a', 'env',
            'MSERIES_REAL_APP_SESSION=1', 'MSERIES_INPUT_TEST_SESSION=1',
            'MSERIES_REAL_APP_TEMP='+scratch, 'GSETTINGS_BACKEND=memory',
            sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]])
        time.sleep(.5)
    raise SystemExit(result.returncode)

assert os.environ.get('GSETTINGS_BACKEND') == 'memory'
output = args.receipt_dir.resolve()
output.mkdir(mode=0o700, parents=True, exist_ok=False)
frozen = output/'evaluated-source'
source = frozen/'dictation'
source.mkdir(parents=True)
(frozen/'local-ai').mkdir()
for path in HERE.glob('*.py'):
    (source/path.name).write_bytes(path.read_bytes())
(frozen/'local-ai/machine.py').write_bytes((HERE.parent/'local-ai/machine.py').read_bytes())
sys.path.insert(0, str(source))
sys.path.insert(0, str(frozen/'local-ai'))
from dictation_resources import snapshot, reasons, load_policy
policy = load_policy()
policy['reserve_gib'] = max(6, policy.get('reserve_gib', 6))
report = {'schema': 1, 'app': args.app, 'complete': False, 'passed': False,
    'fixtures_only': args.fixtures_only, 'source_sha256': {
        p.relative_to(frozen).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in frozen.rglob('*.py')},
    'language': 'English', 'microphone_recorded': False, 'audio_played': False,
    'owner_windows_opened': False, 'owner_profile_loaded': False, 'physical_f5_tested': False,
    'chat_sent': False, 'task_saved': False,
    'method': 'Installed application, synthetic state and actual controller TEST_INSERT; private Xvfb/IBus/session bus',
    'runtime': {'kernel': os.uname().release}, 'field_events': [], 'safety': {}}
samples = []
next_sample = 0
scratch = Path(os.environ['MSERIES_REAL_APP_TEMP'])
for name in ['home', 'runtime', 'config', 'data', 'cache', 'newelle']:
    (scratch/name).mkdir(mode=0o700)
private_env = dict(os.environ, HOME=str(scratch/'home'), XDG_RUNTIME_DIR=str(scratch/'runtime'),
    XDG_CONFIG_HOME=str(scratch/'config'), XDG_DATA_HOME=str(scratch/'data'),
    XDG_CACHE_HOME=str(scratch/'cache'), GSETTINGS_BACKEND='memory', GTK_A11Y='atspi',
    GTK_IM_MODULE='ibus', XMODIFIERS='@im=ibus', GDK_BACKEND='x11',
    GIO_USE_VFS='local', GSK_RENDERER='cairo', LIBGL_ALWAYS_SOFTWARE='1',
    IBUS_ADDRESS='unix:path='+str(scratch/'ibus'))
# Keep the host harness HOME for explicitly pinned installed speech assets only;
# all activated app/EDS/portal helpers inherit a private HOME and private runtime.
for key, value in private_env.items():
    if key != 'HOME':
        os.environ[key] = value
subprocess.run(['dbus-update-activation-environment', 'HOME', 'DISPLAY', 'XAUTHORITY',
    'XDG_RUNTIME_DIR', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME',
    'GSETTINGS_BACKEND', 'GTK_A11Y'], env=private_env, check=True)
import gi
gi.require_version('Atspi', '2.0')
gi.require_version('IBus', '1.0')
from gi.repository import Atspi, IBus, GLib
Atspi.set_timeout(300, 600)
daemon = bridge = application = asr = wm = None
log_handles = []


def checkpoint():
    temp = output/'receipt.tmp'
    temp.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    temp.chmod(0o600)
    os.replace(temp, output/'receipt.json')


def stop(child):
    if child is None:
        return
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait()


def pump(seconds=.1, guard=False):
    global next_sample
    end = time.monotonic()+seconds
    while time.monotonic() < end:
        while GLib.MainContext.default().pending():
            GLib.MainContext.default().iteration(False)
        if guard and time.monotonic() >= next_sample:
            sample = snapshot()
            samples.append(sample)
            next_sample = time.monotonic()+1
            if (reasons(policy, sample=sample)
                or max(sample['fans_rpm'].values(), default=9999) >= 2700
                or max(sample['temperatures_c'].values(), default=999) >= 63):
                raise RuntimeError('Quiet/reserve guard interrupted this owned app trial')
        time.sleep(.01)


def client(method, token=None, text=''):
    command = ['/usr/bin/python3', str(source/'dictation-input-client.py'), method]
    if token:
        command.append(token)
    return subprocess.run(command, input=text, text=True, capture_output=True, timeout=6)


def walk(node):
    todo = [(node, 0)]
    visited = 0
    while todo and visited < 1500:
        item, depth = todo.pop()
        visited += 1
        yield item
        if depth < 32:
            try:
                todo.extend((item.get_child_at_index(n), depth+1)
                            for n in reversed(range(min(item.get_child_count(), 128))))
            except GLib.Error:
                pass


def app_field():
    desktop = Atspi.get_desktop(0)
    for application_node in [desktop.get_child_at_index(i) for i in range(desktop.get_child_count())]:
        name = application_node.get_name().casefold()
        if args.app not in name:
            continue
        candidates = []
        for node in walk(application_node):
            state = node.get_state_set()
            if (int(node.get_role()) in (61, 73, 79, 94, 95)
                and state.contains(Atspi.StateType.EDITABLE)
                and state.contains(Atspi.StateType.SHOWING)
                and (args.app == 'tasks' or state.contains(Atspi.StateType.MULTI_LINE))):
                candidates.append(node)
        report['candidate_fields'] = [dict(name=n.get_name(), role=int(n.get_role())) for n in candidates]
        if candidates:
            return next((n for n in candidates if n.get_state_set().contains(Atspi.StateType.FOCUSED)), candidates[0])
    return None


checkpoint()
try:
    if args.software_wm:
        # No host shell/panel/app startup is inherited by the private compositor.
        (scratch/'config/io.elementary.desktop.wm.shell').write_text('# Private qualification: no panels, dock or shell apps.\n')
        gala = Path('/usr/local/lib/mseries/gala/bin/gala')
        if not gala.exists():
            gala = Path('/usr/bin/gala')
        wm_env = dict(private_env, GALLIUM_DRIVER='llvmpipe', XDG_SESSION_TYPE='x11')
        wm_env.pop('WAYLAND_DISPLAY', None)
        if gala.parent.parent == Path('/usr/local/lib/mseries/gala'):
            wm_env['LD_LIBRARY_PATH'] = str(gala.parent.parent/'lib')
        log = (output/'private-wm.log').open('w')
        log_handles.append(log)
        wm = subprocess.Popen([str(gala)], env=wm_env, stdout=log, stderr=log, start_new_session=True)
        pump(2)
        assert wm.poll() is None, 'Private software window manager exited'
        report['window_manager'] = {'name': 'Gala', 'private_xvfb': True, 'software_rendering': True,
                                   'sha256': hashlib.sha256(gala.read_bytes()).hexdigest()}
    daemon = subprocess.Popen(['ibus-daemon', '--single', '--xim', '--emoji-extension', 'disable',
        '--address', os.environ['IBUS_ADDRESS'], '--cache', 'none'], env=private_env, start_new_session=True)
    pump(1)
    IBus.init()
    bus = IBus.Bus.new()
    assert bus.is_connected()
    bridge = subprocess.Popen(['/usr/bin/python3', str(source/'dictation-input.py')],
                              env=private_env, start_new_session=True)
    pump(1)
    assert bus.set_global_engine('xkb:us::eng')
    if args.app == 'newelle':
        flatpak_env = dict(os.environ, FLATPAK_USER_DIR=str(Path.home()/'.local/share/flatpak'))
        location = subprocess.check_output(['flatpak', 'info', '--show-location', APP],
                                           text=True, env=flatpak_env).strip()
        report['installed_app'] = {'id': APP, 'deployment': Path(location).name}
        helper = scratch/'newelle/helper.py'
        helper.write_bytes((source/'f5-real-apps-qualification.py').read_bytes())
        command = ['flatpak', 'run', '--unshare=network', '--nofilesystem=home', '--nofilesystem=host',
            '--filesystem='+str(scratch), '--socket=session-bus', '--socket=x11', '--command=python3']
        for key in ['HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'GSETTINGS_BACKEND',
                    'GTK_IM_MODULE', 'GTK_A11Y', 'IBUS_ADDRESS', 'GSK_RENDERER', 'LIBGL_ALWAYS_SOFTWARE']:
            command.append('--env='+key+'='+private_env[key])
        command += [APP, str(helper), '--newelle-ui', '--app', 'newelle', '--model', str(args.model),
                    '--receipt-dir', str(scratch/'newelle')]
    else:
        executable = '/usr/bin/io.elementary.'+args.app
        report['installed_app'] = {'executable': Path(executable).name,
            'sha256': hashlib.sha256(Path(executable).read_bytes()).hexdigest()}
        blank = scratch/'synthetic.txt'
        blank.write_text('')
        command = [executable, '--new-window', str(blank)] if args.app == 'code' else [executable]
    log = (output/'private-app.log').open('w')
    log_handles.append(log)
    application = subprocess.Popen(command, env=flatpak_env if args.app == 'newelle' else private_env,
                                   stdout=log, stderr=log, start_new_session=True)
    field = None
    end = time.monotonic()+30
    while field is None:
        if application.poll() is not None:
            raise RuntimeError('Installed app exited before exposing a synthetic text field')
        pump(.2)
        if args.app == 'newelle':
            ui = scratch/'newelle/ui.json'
            if not ui.exists() or not json.loads(ui.read_text()).get('ready'):
                if time.monotonic() > end:
                    raise TimeoutError('Installed Newelle composer unavailable in isolated profile')
                continue
        field = app_field()
        if time.monotonic() > end:
            report.update(complete=True, qualification_status='unsupported-empty-profile-route')
            raise RuntimeError('No supported editable field in isolated installed app; unscored')
    # GTK4's AT-SPI Component.GrabFocus can be unsupported. A bounded XTest
    # click is restricted to this fixture's private Xvfb display and app field.
    if args.app != 'newelle':
        rect = Atspi.Component.get_extents(field, Atspi.CoordType.SCREEN)
        x11 = ctypes.CDLL('libX11.so.6')
        xtst = ctypes.CDLL('libXtst.so.6')
        x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
        x11.XOpenDisplay.restype = ctypes.c_void_p
        x11.XFlush.argtypes = [ctypes.c_void_p]
        x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
        x11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        xtst.XTestFakeMotionEvent.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_ulong]
        xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
        display = x11.XOpenDisplay(None)
        assert display and rect.width > 0 and rect.height > 0
        try:
            tree = subprocess.check_output(['xwininfo', '-root', '-tree'], text=True)
            for line in tree.splitlines():
                match = re.search(r'(0x[0-9a-f]+)\s+"([^"]+)"', line)
                if match:
                    geometry = re.search(r'(\d+)x(\d+)[+-]', line)
                    if geometry is None or int(geometry[1]) < 200 or int(geometry[2]) < 100:
                        continue  # Gtk's hidden 1x1 application leader is not an input window.
                    prop = subprocess.run(['xprop', '-id', match[1], '_NET_WM_PID'],
                                          capture_output=True, text=True, timeout=2)
                    if prop.stdout.strip().endswith('= '+str(application.pid)):
                        x11.XSetInputFocus(display, int(match[1], 16), 1, 0)
                        report['private_window_focused_by_pid'] = True
                        break
            xtst.XTestFakeMotionEvent(display, 0, rect.x+min(20, rect.width//2), rect.y+min(20, rect.height//2), 0)
            xtst.XTestFakeButtonEvent(display, 1, 1, 0)
            xtst.XTestFakeButtonEvent(display, 1, 0, 0)
            x11.XFlush(display)
        finally:
            x11.XCloseDisplay(display)
    pump(1)
    report['field_metadata'] = {'role': int(field.get_role()), 'name': field.get_name(),
                               'editable': True, 'synthetic_state': True}
    started_metadata = time.monotonic()
    node = field
    ancestors = []
    for _ in range(32):
        if node is None:
            break
        node.clear_cache()
        state = node.get_state_set()
        ancestors.append({'role': int(node.get_role()),
            'active': state.contains(Atspi.StateType.ACTIVE),
            'focused': state.contains(Atspi.StateType.FOCUSED)})
        node = node.get_parent()
    report['field_metadata']['ancestors'] = ancestors
    report['field_metadata']['metadata_elapsed_s'] = time.monotonic()-started_metadata
    def text():
        field.clear_cache()
        return Atspi.Text.get_text(field, 0, -1)
    assert text() == '', 'Fresh app target is not an empty synthetic field'
    result = client('begin')
    assert result.returncode == 0, result.stderr
    token = result.stdout.strip()
    assert client('preview', token, 'Temporary English preview').returncode == 0
    pump(.3)
    assert client('cancel').returncode == 0
    pump(.3)
    assert text() == '', 'Cancel retained provisional words in the installed app'
    assert client('commit', token, 'stale words').returncode != 0
    assert bus.get_global_engine().get_name() == 'xkb:us::eng'
    report['safety'].update(cancel_clears_provisional=True, cancel_revokes_lease=True,
                            native_engine_restored=True)
    checkpoint()
    if not args.fixtures_only:
        stable = 0
        end = time.monotonic()+900
        while stable < 3:
            sample = snapshot()
            busy = subprocess.run(['pgrep', '-x', 'oha|rustc'], capture_output=True).returncode == 0
            cool = (not busy and not reasons(policy, extra_bytes=2*1024**3, sample=sample)
                and max(sample['fans_rpm'].values(), default=9999) < 2700
                and max(sample['temperatures_c'].values(), default=999) < 60)
            stable = stable+1 if cool else 0
            if time.monotonic() > end:
                raise TimeoutError('No quiet admission window; no speech quality score')
            pump(2)
        native = Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'
        report['runtime'].update(engine='nemotron', backend='cpu', threads=4,
            library_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
            model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
            wav_sha256=hashlib.sha256(args.wav.read_bytes()).hexdigest())
        env = dict(os.environ, STREAM_OUTPUT='ibus', STREAM_TEST_INSERT='1',
            STREAM_TEST_WAV=str(args.wav.resolve()), STREAM_MODEL=str(args.model.resolve()),
            STREAM_ENGINE='nemotron', STREAM_BACKEND='cpu', STREAM_THREADS='4',
            STREAM_QUIET='1', STREAM_POPUP='0', STREAM_UNVERIFIED_FALLBACK='0', TRANSCRIBE_LIBRARY=str(native))
        for key in ['STREAM_DRY', 'STREAM_TEST_RAW', 'STREAM_KEEP']:
            env.pop(key, None)
        with wave.open(str(args.wav), 'rb') as audio:
            duration = audio.getnframes()/audio.getframerate()
        started = time.monotonic()
        log = (output/'private-controller.log').open('w')
        log_handles.append(log)
        asr = subprocess.Popen([str(Path.home()/'.local/share/mseries/stream/venv/bin/python'),
            '-I', str(source/'stream-dictate.py')], env=env, stdout=log, stderr=log, start_new_session=True)
        previous = ''
        while asr.poll() is None:
            if time.monotonic()-started > 100:
                raise TimeoutError('Owned file-input app trial exceeded deadline')
            pump(.05, guard=True)
            current = text()
            if current != previous:
                report['field_events'].append({'elapsed_s': time.monotonic()-started, 'text': current})
                previous = current
        pump(.2, guard=True)
        assert asr.returncode == 0, 'Controller failed; preserve private log'
        actual = text()
        first = next((x['elapsed_s'] for x in report['field_events'] if x['text']), None)
        report['speech'] = {'final_text': actual, 'reference': REFERENCE,
            'first_committed_text_s': first, 'audio_duration_s': duration,
            'elapsed_s': time.monotonic()-started,
            'provisional_scope': 'Toolkit-native preedit qualified separately; this external app trace observes committed accessible text'}
        if args.app == 'newelle' and (scratch/'newelle/ui.json').exists():
            ui = json.loads((scratch/'newelle/ui.json').read_text())
            report['speech']['provisional_events'] = [dict(elapsed_s=x['monotonic_s']-started, text=x['text'])
                for x in ui['preedit'] if x['monotonic_s'] >= started]
        checkpoint()
        assert re.findall(r'\w+', actual.casefold()) == re.findall(r'\w+', REFERENCE.casefold()), 'Final English words differ from public reference'
        assert first is not None and first < duration, 'No early visible committed text in the actual app'
        assert bus.get_global_engine().get_name() == 'xkb:us::eng'
        report['speech'].update(exact_normalized_words=True, native_engine_restored=True)
    report.update(complete=True, passed=True)
except Exception as error:
    report['failure_kind'] = type(error).__name__
    report['failure_detail'] = str(error)[:500]
    report['failure_scope'] = 'Retain attempt and completed stages; unavailable/interrupted runtime routes are unscored'
    raise
finally:
    if samples:
        report['resources'] = {'samples': len(samples),
            'min_available_bytes': min(x['available_bytes'] for x in samples),
            'max_fan_rpm': max(max(x['fans_rpm'].values(), default=9999) for x in samples),
            'max_temp_c': max(max(x['temperatures_c'].values(), default=999) for x in samples)}
    checkpoint()
    for child in [asr, application, bridge, daemon, wm]:
        stop(child)
    for handle in log_handles:
        handle.close()
print(json.dumps({'app': args.app, 'passed': report['passed'], 'complete': report['complete'],
                  'fixtures_only': args.fixtures_only, 'microphone_recorded': False}))
