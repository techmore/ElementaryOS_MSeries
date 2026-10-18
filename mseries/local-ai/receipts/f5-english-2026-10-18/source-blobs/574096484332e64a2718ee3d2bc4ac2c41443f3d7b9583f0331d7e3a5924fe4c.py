#!/usr/bin/python3
"""File-input F5 controller acceptance in one isolated real application toolkit.

No physical F5, microphone, owner profile, owner window, clipboard, or playback is
used. TEST_INSERT calls the same Dictation.start/controller/final-drain path as
F5. Run each framework serially under the existing quiet qualification queue.
--fixtures-only verifies the app/input boundary without loading any speech model.
"""
import argparse
import contextlib
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
import urllib.parse
import urllib.request
import wave

HERE = Path(__file__).resolve().parent
REFERENCE = ('He hoped there would be stew for dinner, turnips and carrots and bruised '
             'potatoes and fat mutton pieces to be ladled out in thick, peppered, '
             'flour-fattened sauce')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--framework', choices=['gtk3', 'gtk4', 'qt6', 'brave'], required=True)
parser.add_argument('--receipt-dir', type=Path, required=True)
parser.add_argument('--wav', type=Path, default=Path.home()/'.local/share/mseries/stream/libri.wav')
parser.add_argument('--model', type=Path, default=Path.home()/'.local/share/mseries/stream/models/nemotron-speech-streaming-en-0.6b-Q8_0.gguf')
parser.add_argument('--fixtures-only', action='store_true')
args = parser.parse_args()
if os.environ.get('MSERIES_F5_APP_SESSION') != '1':
    # Release temporary portal mounts after the owning private session bus has
    # gone away, not while its activated document portal still holds the mount.
    with tempfile.TemporaryDirectory(prefix='mseries-f5-app-') as scratch:
        result = subprocess.run(['dbus-run-session', '--', 'xvfb-run', '-a', 'env',
            'MSERIES_F5_APP_SESSION=1', 'MSERIES_INPUT_TEST_SESSION=1', 'GSETTINGS_BACKEND=memory',
            'MSERIES_F5_TEMP='+scratch,
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
# Freeze complete public Python modules so imported helpers and this driver can
# be audited even when the working checkout changes during a longer queue.
for path in HERE.glob('*.py'):
    (source/path.name).write_bytes(path.read_bytes())
(frozen/'local-ai/machine.py').write_bytes((HERE.parent/'local-ai/machine.py').read_bytes())
hashes = {p.relative_to(frozen).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
          for p in frozen.rglob('*.py')}
sys.path.insert(0, str(source))
sys.path.insert(0, str(frozen/'local-ai'))
from dictation_resources import snapshot, reasons, load_policy

report = {'schema': 1, 'complete': False, 'passed': False, 'framework': args.framework,
          'fixtures_only': args.fixtures_only, 'source_sha256': hashes,
          'microphone_recorded': False, 'audio_played': False,
          'owner_windows_opened': False, 'keyboard_device_opened': False,
          'physical_f5_tested': False, 'language': 'English',
          'method': 'Public file through actual F5 controller TEST_INSERT in private Xvfb/IBus/session bus',
          'safety': {}, 'field_events': [], 'provisional_events': [],
          'runtime': {'kernel': os.uname().release}}
samples = []
policy = load_policy()
policy['reserve_gib'] = max(6, policy.get('reserve_gib', 6))
next_sample = 0


def checkpoint():
    temp = output/'receipt.tmp'
    temp.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n')
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


checkpoint()
with contextlib.nullcontext(os.environ['MSERIES_F5_TEMP']) as directory:
    runtime = Path(directory)/'runtime'
    runtime.mkdir(mode=0o700)
    os.environ.update(IBUS_ADDRESS='unix:path='+directory+'/bus', XMODIFIERS='@im=ibus',
        GTK_IM_MODULE='ibus', QT_IM_MODULE='ibus', GDK_BACKEND='x11',
        QT_QPA_PLATFORM='xcb', QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1', GTK_A11Y='atspi',
        GIO_USE_VFS='local', GSK_RENDERER='cairo', LIBGL_ALWAYS_SOFTWARE='1',
        XDG_CACHE_HOME=directory+'/cache', XDG_CONFIG_HOME=directory+'/config', XDG_RUNTIME_DIR=str(runtime))
    # This is the private dbus-run-session bus, without --systemd. Private
    # activated portals/accessibility helpers must not inherit the owner runtime.
    subprocess.run(['dbus-update-activation-environment', 'XDG_RUNTIME_DIR', 'DISPLAY',
                    'XAUTHORITY', 'XDG_CACHE_HOME', 'XDG_CONFIG_HOME', 'GSETTINGS_BACKEND'], check=True)
    import gi
    gi.require_version('IBus', '1.0')
    from gi.repository import IBus, Gio, GLib
    daemon = engine = browser = asr = None
    app = window = ws = None
    speech_started = None

    def preedit(text):
        if speech_started is not None:
            report['provisional_events'].append({'elapsed_s': time.monotonic()-speech_started, 'text': text})

    def measure():
        global next_sample
        if time.monotonic() < next_sample:
            return
        item = snapshot()
        samples.append(item)
        next_sample = time.monotonic()+1
        # The 2700 RPM/63 C trial limits are stricter than the normal policy.
        if (reasons(policy, sample=item) or max(item['fans_rpm'].values(), default=9999) >= 2700
                or max(item['temperatures_c'].values(), default=999) >= 63):
            raise RuntimeError('Quiet/reserve guard interrupted this owned app trial')

    def pump(seconds=.1, guarded=False):
        end = time.monotonic()+seconds
        while time.monotonic() < end:
            if args.framework == 'qt6' and app:
                app.processEvents()
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            if guarded:
                measure()
            time.sleep(.01)

    def client(method, token=None, text=''):
        command = ['/usr/bin/python3', str(source/'dictation-input-client.py'), method]
        if token:
            command.append(token)
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True)
        child.stdin.write(text)
        child.stdin.close()
        child.stdin = None
        end = time.monotonic()+6
        while child.poll() is None:
            if time.monotonic() > end:
                child.kill()
                child.wait()
                raise TimeoutError('Private input client expired')
            pump(.02)
        out, err = child.communicate()
        return subprocess.CompletedProcess(command, child.returncode, out, err)

    try:
        daemon = subprocess.Popen(['ibus-daemon', '--single', '--xim', '--emoji-extension', 'disable',
            '--address', os.environ['IBUS_ADDRESS'], '--cache', 'none'], start_new_session=True)
        time.sleep(1)
        IBus.init()
        bus = IBus.Bus.new()
        assert bus.is_connected()
        engine = subprocess.Popen(['/usr/bin/python3', str(source/'dictation-input.py')], start_new_session=True)
        pump(1)
        assert bus.set_global_engine('xkb:us::eng')

        if args.framework.startswith('gtk'):
            version = '4.0' if args.framework == 'gtk4' else '3.0'
            gi.require_version('Gtk', version)
            gi.require_version('Gdk', version)
            from gi.repository import Gtk, Gdk
            window = Gtk.Window(title='Private English F5 acceptance')
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            window.set_child(box) if version == '4.0' else window.add(box)
            first, second, password = Gtk.Entry(), Gtk.Entry(), Gtk.Entry()
            password.set_visibility(False)
            password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
            for field in [first, second, password]:
                box.append(field) if version == '4.0' else box.pack_start(field, False, False, 0)
            if version == '3.0':
                window.show_all()
            window.present()
            pump()
            (window.get_surface() if version == '4.0' else window.get_window()).focus(Gdk.CURRENT_TIME)
            get = lambda field: field.get_text()
            clear = lambda field: field.set_text('')
            focus = lambda field: field.grab_focus()
            target = first.get_delegate() if version == '4.0' else first
            target.connect('preedit-changed', lambda widget, text: preedit(text))
        elif args.framework == 'qt6':
            from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLineEdit
            class TracedLineEdit(QLineEdit):
                def inputMethodEvent(self, event):
                    preedit(event.preeditString())
                    super().inputMethodEvent(event)
            app = QApplication([])
            window = QWidget()
            layout = QVBoxLayout(window)
            first, second, password = TracedLineEdit(), QLineEdit(), QLineEdit()
            password.setEchoMode(QLineEdit.EchoMode.Password)
            for field in [first, second, password]:
                layout.addWidget(field)
            window.show()
            window.activateWindow()
            pump()
            x11 = ctypes.CDLL('libX11.so.6')
            x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
            x11.XOpenDisplay.restype = ctypes.c_void_p
            x11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
            x11.XFlush.argtypes = [ctypes.c_void_p]
            x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
            display = x11.XOpenDisplay(None)
            assert display
            try:
                x11.XSetInputFocus(display, int(window.winId()), 1, 0)
                x11.XFlush(display)
            finally:
                x11.XCloseDisplay(display)
            get = lambda field: field.text()
            clear = lambda field: field.clear()
            focus = lambda field: field.setFocus()
        else:
            from websockets.sync.client import connect
            # Accessibility is enabled on this new private session bus only.
            conn = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            conn.call_sync('org.a11y.Bus', '/org/a11y/bus', 'org.freedesktop.DBus.Properties', 'Set',
                GLib.Variant('(ssv)', ('org.a11y.Status', 'IsEnabled', GLib.Variant('b', True))),
                None, Gio.DBusCallFlags.NONE, 3000, None)
            profile = Path(directory)/'browser-profile'
            browser = subprocess.Popen(['brave-browser', '--user-data-dir='+str(profile),
                '--ozone-platform=x11', '--disable-gpu', '--disable-background-networking',
                '--disable-extensions', '--disable-sync', '--no-first-run', '--no-default-browser-check',
                '--password-store=basic', '--remote-debugging-address=127.0.0.1',
                '--remote-debugging-port=0', '--host-resolver-rules=MAP * ~NOTFOUND',
                '--force-renderer-accessibility', 'about:blank'], stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, start_new_session=True)
            end = time.monotonic()+15
            while not (profile/'DevToolsActivePort').exists():
                assert browser.poll() is None, 'Private browser exited'
                if time.monotonic() > end:
                    raise TimeoutError('Private browser debugging socket unavailable')
                pump()
            port = int((profile/'DevToolsActivePort').read_text().splitlines()[0])
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=3) as response:
                page = next(x for x in json.load(response) if x['type'] == 'page')
            ws = connect(page['webSocketDebuggerUrl'], proxy=None, open_timeout=3)
            sequence = 0

            def cdp(method, params=None):
                global sequence
                sequence += 1
                ws.send(json.dumps({'id': sequence, 'method': method, 'params': params or {}}))
                while True:
                    row = json.loads(ws.recv(timeout=5))
                    if row.get('id') == sequence:
                        if 'error' in row:
                            raise RuntimeError(row['error'])
                        return row.get('result', {})

            def js(expression):
                return cdp('Runtime.evaluate', {'expression': expression, 'returnByValue': True})['result'].get('value')

            html = '<meta charset="utf-8"><input id="first"><textarea id="second"></textarea><input id="password" type="password">'
            cdp('Page.navigate', {'url': 'data:text/html,'+urllib.parse.quote(html)})
            pump(1)
            cdp('Page.bringToFront')
            js("window.preeditEvents=[];window.composing=false;window.committedText='';const input=document.getElementById('first');input.addEventListener('compositionstart',()=>{window.committedText=input.value;window.composing=true});input.addEventListener('compositionend',()=>window.composing=false);input.addEventListener('compositionupdate',e=>window.preeditEvents.push({milliseconds:performance.now(),text:e.data}));input.addEventListener('input',e=>{if(!e.isComposing)window.committedText=input.value});window.preeditStart=0")
            first, second, password = 'first', 'second', 'password'
            get = lambda field: js('document.getElementById('+json.dumps(field)+').value')
            clear = lambda field: js('document.getElementById('+json.dumps(field)+').value=""')
            focus = lambda field: js('document.getElementById('+json.dumps(field)+').focus()')

        focus(first)
        pump(1)
        result = client('begin')
        assert result.returncode == 0, result.stderr
        token = result.stdout.strip()
        assert client('check', token).returncode == 0
        speech_started = time.monotonic()
        assert client('preview', token, 'Temporary English preview').returncode == 0
        pump()
        if args.framework != 'brave':
            assert get(first) == '', 'Provisional text was permanently inserted'
        if args.framework == 'brave':
            fixture_preview = js('window.preeditEvents.map(x=>x.text)')
            js('window.preeditEvents=[]')
        else:
            fixture_preview = [x['text'] for x in report['provisional_events']]
        assert not any(fixture_preview), 'Speculative preview appeared despite the focus-safety policy'
        assert client('preview', token, '').returncode == 0
        pump()
        assert get(first) == '', 'Clearing provisional text left inserted words'
        report['safety']['speculative_preview_suppressed'] = True
        report['provisional_events'] = []
        speech_started = None
        literal = 'English literal: $() & <tag> "quoted".'
        assert client('commit', token, literal).returncode == 0
        pump()
        assert get(first) == literal
        assert client('cancel').returncode == 0
        assert client('commit', token, ' stale').returncode != 0
        assert get(first) == literal
        assert bus.get_global_engine().get_name() == 'xkb:us::eng'
        report['safety']['cancel_revokes_lease_and_restores_engine'] = True
        clear(first)
        result = client('begin')
        assert result.returncode == 0, result.stderr
        token = result.stdout.strip()
        focus(second)
        pump()
        assert client('check', token).returncode != 0
        assert client('commit', token, 'wrong field').returncode != 0
        assert get(second) == ''
        assert client('finish', token).returncode == 0
        report['safety']['focus_change_rejected_and_other_field_untouched'] = True
        focus(password)
        pump()
        assert client('begin').returncode != 0
        assert get(password) == ''
        report['safety']['password_refused_and_untouched'] = True
        checkpoint()

        if not args.fixtures_only:
            # Wait for a cool window; do not stop or change other owner work.
            stable = 0
            end = time.monotonic()+900
            while stable < 3:
                item = snapshot()
                busy = subprocess.run(['pgrep', '-x', 'oha|rustc'], capture_output=True).returncode == 0
                cool = (not busy and not reasons(policy, sample=item, extra_bytes=2*1024**3)
                    and max(item['fans_rpm'].values(), default=9999) < 2700
                    and max(item['temperatures_c'].values(), default=999) < 60)
                stable = stable+1 if cool else 0
                if time.monotonic() > end:
                    raise TimeoutError('No quiet admission window; model trial unscored')
                pump(2)
            focus(first)
            clear(first)
            pump(1)
            native = Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'
            report['runtime'].update(engine='nemotron', backend='cpu', threads=4,
                library_sha256=hashlib.sha256(native.read_bytes()).hexdigest(),
                model_sha256=hashlib.sha256(args.model.read_bytes()).hexdigest(),
                wav_sha256=hashlib.sha256(args.wav.read_bytes()).hexdigest())
            with wave.open(str(args.wav), 'rb') as audio:
                duration = audio.getnframes()/audio.getframerate()
            env = dict(os.environ, STREAM_OUTPUT='ibus', STREAM_TEST_INSERT='1',
                STREAM_TEST_WAV=str(args.wav.resolve()), STREAM_ENGINE='nemotron',
                STREAM_MODEL=str(args.model.resolve()), STREAM_BACKEND='cpu', STREAM_THREADS='4',
                STREAM_QUIET='1', STREAM_POPUP='0', STREAM_UNVERIFIED_FALLBACK='0',
                TRANSCRIBE_LIBRARY=str(native))
            for key in ['STREAM_DRY', 'STREAM_KEEP', 'STREAM_TEST_RAW']:
                env.pop(key, None)
            started = time.monotonic()
            speech_started = started
            if args.framework == 'brave':
                js('window.preeditStart=performance.now()')
            last = ''
            with (output/'private-controller.log').open('w') as log:
                asr = subprocess.Popen([str(Path.home()/'.local/share/mseries/stream/venv/bin/python'),
                    '-I', str(source/'stream-dictate.py')], env=env, stdout=log,
                    stderr=log, start_new_session=True)
                while asr.poll() is None:
                    if time.monotonic()-started > 100:
                        raise TimeoutError('Owned file-input controller exceeded deadline')
                    pump(.05, guarded=True)
                    text = (js('window.composing?window.committedText:document.getElementById("first").value')
                            if args.framework == 'brave' else get(first))
                    if text != last:
                        report['field_events'].append({'elapsed_s': time.monotonic()-started, 'text': text})
                        last = text
                pump(.2, guarded=True)
                assert asr.returncode == 0, 'Controller failed; retain private log'
            actual = get(first)
            if args.framework == 'brave':
                report['provisional_events'] = js('window.preeditEvents.map(x=>({elapsed_s:(x.milliseconds-window.preeditStart)/1000,text:x.text}))')
            if not report['field_events'] or report['field_events'][-1]['text'] != actual:
                report['field_events'].append({'elapsed_s': time.monotonic()-started, 'text': actual})
            report['speech'] = {'final_text': actual, 'reference': REFERENCE,
                'first_widget_text_s': next((x['elapsed_s'] for x in report['field_events'] if x['text']), None),
                'first_provisional_s': next((x['elapsed_s'] for x in report['provisional_events'] if x['text']), None),
                'audio_duration_s': duration,
                'elapsed_s': time.monotonic()-started, 'actual_controller_started': True}
            checkpoint()
            assert re.findall(r'\w+', actual.casefold()) == re.findall(r'\w+', REFERENCE.casefold()), 'Final English words differ from public reference'
            visible = [report['speech'][key] for key in ['first_provisional_s', 'first_widget_text_s']
                       if report['speech'][key] is not None]
            assert visible and min(visible) < duration, 'First visible text arrived after the nominal audio ended'
            report['speech']['first_visible_text_s'] = min(visible)
            assert bus.get_global_engine().get_name() == 'xkb:us::eng'
            report['speech'].update(exact_normalized_words=True, native_engine_restored=True)
        report.update(complete=True, passed=True)
    except Exception as error:
        report['failure_kind'] = type(error).__name__
        report['failure_detail'] = str(error)[:500]
        report['failure_scope'] = 'Retain this attempt and completed stages; no quality score for interrupted/unstarted speech'
        raise
    finally:
        if samples:
            report['resources'] = {'samples': len(samples),
                'min_available_bytes': min(x['available_bytes'] for x in samples),
                'max_fan_rpm': max(max(x['fans_rpm'].values(), default=9999) for x in samples),
                'max_temp_c': max(max(x['temperatures_c'].values(), default=999) for x in samples)}
        checkpoint()
        stop(asr)
        if ws:
            ws.close()
        stop(browser)
        if window:
            window.close() if args.framework == 'qt6' else window.destroy()
        stop(engine)
        stop(daemon)
print(json.dumps({'framework': args.framework, 'passed': report['passed'], 'complete': report['complete'],
                  'fixtures_only': args.fixtures_only, 'microphone_recorded': False}))
