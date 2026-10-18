#!/usr/bin/python3
"""Synthetic GTK fields on a private IBus/Xvfb session; no microphone or global keys.
Run: dbus-run-session -- xvfb-run -a python3 mseries/dictation/gtk-input-smoke.py
"""
import json
import argparse
import sys
import os
from pathlib import Path
import subprocess
import tempfile
import time
import hashlib
import ctypes
import re
import signal

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gtk4',action='store_true')
parser.add_argument('--receipt-dir',type=Path,help='New private output folder for exact evaluated sources and bounded receipt')
parser.add_argument('--reconnect-check',action='store_true',help='Private IBus reconnect and selected-source recovery; synthetic fields only')
parser.add_argument('--keyboard-check',action='store_true',help='Synthetic ordinary-key and US-international compose regression in private Xvfb')
parser.add_argument('--speech-file',type=Path,help='Public synthetic test WAV; CPU ASR, no microphone')
parser.add_argument('--lifecycle-check',action='store_true',help='One public-file run plus native model close/reload, no second inference')
parser.add_argument('--wayland',action='store_true',help='Use only inside an isolated nested Wayland desktop')
args=parser.parse_args()
if args.lifecycle_check:assert args.speech_file and not args.wayland,'Lifecycle fixture requires the public-file private X11 path'
if args.reconnect_check:assert not args.wayland and not args.speech_file,'Reconnect fixture uses private X11/keyfile settings; no ASR'
if args.wayland:
    assert os.environ.get('MSERIES_DICTATION_TEST_BUS') == '1' and os.environ.get('GSETTINGS_BACKEND') == 'memory', 'Use test-wayland-input.sh'
elif os.environ.get('MSERIES_INPUT_TEST_SESSION') != '1':
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env',
        'MSERIES_INPUT_TEST_SESSION=1','GSETTINGS_BACKEND=memory',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]]).returncode)
with tempfile.TemporaryDirectory(prefix='mseries-gtk-input-') as directory:
    os.environ.update(IBUS_ADDRESS='unix:path='+directory+'/bus', GTK_IM_MODULE='ibus',
        GDK_BACKEND='wayland' if args.wayland else 'x11', XDG_CACHE_HOME=directory+'/cache', XDG_CONFIG_HOME=directory+'/config',
        GTK_A11Y='atspi', GIO_USE_VFS='local',GSK_RENDERER='cairo',LIBGL_ALWAYS_SOFTWARE='1')
    if args.reconnect_check:os.environ['GSETTINGS_BACKEND']='keyfile'
    evaluated=Path(directory)/'evaluated-source'
    if args.receipt_dir:
        args.receipt_dir=args.receipt_dir.resolve()
        args.receipt_dir.mkdir(mode=0o700,parents=True,exist_ok=False)
        evaluated=args.receipt_dir/'evaluated-source'
    evaluated.mkdir(mode=0o700)
    source_hashes={}
    for name in ['stream-dictate.py','dictation-input.py','dictation-input-client.py','dictation_status.py','dictation_resources.py','dictation_model.py','lifecycle-smoke.py','gtk-input-smoke.py']:
        raw=Path(__file__).with_name(name).read_bytes()
        (evaluated/name).write_bytes(raw)
        source_hashes[name]=hashlib.sha256(raw).hexdigest()
    raw=(Path(__file__).resolve().parent.parent/'local-ai/machine.py').read_bytes()
    (evaluated/'machine.py').write_bytes(raw);source_hashes['machine.py']=hashlib.sha256(raw).hexdigest()
    import gi
    gi.require_version('IBus','1.0')
    gi.require_version('Gtk','4.0' if args.gtk4 else '3.0')
    gi.require_version('Gdk','4.0' if args.gtk4 else '3.0')
    from gi.repository import IBus,Gio,GLib,Gtk,Gdk
    if args.reconnect_check:
        native=Gio.Settings.new('org.gnome.desktop.input-sources')
        assert native.set_value('sources',GLib.Variant('a(ss)',[('xkb','us')]))
        native.set_uint('current',0);Gio.Settings.sync()
    daemon=subprocess.Popen(['ibus-daemon','--single','--emoji-extension','disable',
        '--address',os.environ['IBUS_ADDRESS'],'--cache','none'])
    engine=None
    def pump(seconds=.3):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            time.sleep(.01)
    try:
        time.sleep(1);IBus.init();bus=IBus.Bus.new();assert bus.is_connected()
        engine=subprocess.Popen(['/usr/bin/python3',str(evaluated/'dictation-input.py')])
        pump(1)
        subprocess.run(['/usr/bin/python3',str(evaluated/'dictation-input-client.py'),'select','xkb:us::eng'],check=True)
        window=Gtk.Window(title='Synthetic dictation fields');box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        window.set_child(box) if args.gtk4 else window.add(box)
        first,second,password=Gtk.Entry(),Gtk.Entry(),Gtk.Entry()
        password.set_visibility(False);password.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        for entry in [first,second,password]:
            if args.gtk4:box.append(entry)
            else:box.pack_start(entry,False,False,0)
        if not args.gtk4:window.show_all()
        window.present();pump()
        (window.get_surface() if args.gtk4 else window.get_window()).focus(Gdk.CURRENT_TIME)
        first.grab_focus();pump(1)
        keyboard_receipt=None
        if args.keyboard_check:
            assert not args.wayland,'XTest keyboard fixture requires private Xvfb'
            subprocess.run(['/usr/bin/python3',str(evaluated/'dictation-input-client.py'),'select'],check=True)
            subprocess.run(['setxkbmap','-layout','us','-variant','intl'],check=True)
            x11=ctypes.CDLL('libX11.so.6');xtst=ctypes.CDLL('libXtst.so.6')
            x11.XOpenDisplay.argtypes=[ctypes.c_char_p];x11.XOpenDisplay.restype=ctypes.c_void_p
            x11.XKeysymToKeycode.argtypes=[ctypes.c_void_p,ctypes.c_ulong];x11.XKeysymToKeycode.restype=ctypes.c_uint
            x11.XFlush.argtypes=[ctypes.c_void_p];x11.XCloseDisplay.argtypes=[ctypes.c_void_p]
            xtst.XTestFakeKeyEvent.argtypes=[ctypes.c_void_p,ctypes.c_uint,ctypes.c_int,ctypes.c_ulong]
            display=x11.XOpenDisplay(None);assert display
            def key(symbol,down):
                code=x11.XKeysymToKeycode(display,symbol);assert code
                assert xtst.XTestFakeKeyEvent(display,code,int(down),0)
                x11.XFlush(display);pump(.05)
            def tap(symbol):key(symbol,True);key(symbol,False)
            try:
                first.set_text('');tap(ord('a'));key(0xffe1,True);tap(ord('b'));key(0xffe1,False);pump()
                assert first.get_text()=='aB',repr(first.get_text())
                tap(0xff08);assert first.get_text()=='a'
                first.set_text('');tap(0xfe51);tap(ord('e'));pump()
                assert first.get_text()=='é',repr(first.get_text())
                keyboard_receipt={'ordinary_keys':True,'shift':True,'backspace':True,'dead_key_compose':True,'layout':'private Xvfb us(intl)'}
                first.set_text('');pump()
            finally:x11.XCloseDisplay(display)
            subprocess.run(['/usr/bin/python3',str(evaluated/'dictation-input-client.py'),'select','xkb:us::eng'],check=True)
        conn=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        def call(method,args=None):
            return conn.call_sync('org.techmore.DictationInput','/org/techmore/DictationInput',
                'org.techmore.DictationInput',method,args,None,Gio.DBusCallFlags.NONE,2000,None)
        client=['/usr/bin/python3',str(evaluated/'dictation-input-client.py')]
        def run_client(method,token=None,text=''):
            command=client+[method]+([token] if token else [])
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            process.stdin.write(text);process.stdin.close();process.stdin=None
            deadline=time.monotonic()+5
            while process.poll() is None:
                if time.monotonic()>deadline:
                    process.kill();process.wait();raise TimeoutError('Bounded client request expired')
                pump(.02)
            stdout,stderr=process.communicate()
            return subprocess.CompletedProcess(command,process.returncode,stdout,stderr)
        result=run_client('begin');assert result.returncode==0,result.stderr
        token=result.stdout.strip()
        assert run_client('check',token).returncode==0
        assert not first.get_text(),'Pre-capture check inserted text'
        text='Café — 日本語 + & $(literal)'
        for chunk in [text[:8],text[8:]]:
            result=run_client('commit',token,chunk);assert result.returncode==0,result.stderr
            pump()
        assert first.get_text()==text,first.get_text()
        assert run_client('begin').returncode!=0,'Overlapping Begin replaced the session'
        assert run_client('finish',token).returncode==0
        pump()
        assert bus.get_global_engine().get_name()=='xkb:us::eng','Finish did not restore original engine'
        result=run_client('begin');assert result.returncode==0,result.stderr
        token=result.stdout.strip()
        assert bus.get_global_engine().get_name()=='mseries-dictation'
        assert run_client('cancel').returncode==0
        pump()
        assert bus.get_global_engine().get_name()=='xkb:us::eng','Cancel did not restore original engine'
        assert run_client('commit',token,'cancelled').returncode!=0
        speech_receipt=None
        if args.speech_file:
            sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'local-ai'))
            from machine import snapshot,violations,DEFAULT_POLICY
            policy_path=Path.home()/'.config/mseries-ai/profiles.json'
            policy=json.loads(policy_path.read_text())['policy'] if policy_path.exists() else DEFAULT_POLICY
            stable=0
            while stable<3:
                sample=snapshot()
                busy=subprocess.run(['pgrep','-x','oha|rustc'],capture_output=True).returncode==0
                ready=not busy and not violations(sample,policy,1024**3) and max(sample['fans_rpm'].values(),default=9999)<2700 and max(sample['temperatures_c'].values(),default=999)<=63
                stable=stable+1 if ready else 0
                if not ready:print('Waiting for quiet CPU speech test admission; owner jobs preserved',flush=True)
                pump(10)
            first.set_text('');first.grab_focus();pump()
            env=dict(os.environ,STREAM_OUTPUT='ibus',STREAM_TEST_INSERT='1',STREAM_TEST_WAV=str(args.speech_file.resolve()),
                STREAM_BACKEND='cpu',STREAM_THREADS='6',STREAM_QUIET='1')
            env.pop('STREAM_DRY',None);env.pop('STREAM_TEST_RAW',None);env.pop('STREAM_KEEP',None)
            env['TRANSCRIBE_LIBRARY']=str(Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so')
            started=time.monotonic();first_text_s=None;samples=[]
            log=(args.receipt_dir or Path(directory))/'private-asr.log'
            with log.open('w') as output:
                command=[str(Path.home()/'.local/share/mseries/stream/venv/bin/python'),'-I',str(evaluated/('lifecycle-smoke.py' if args.lifecycle_check else 'stream-dictate.py'))]
                if args.lifecycle_check:command+=['--receipt',str((args.receipt_dir or Path(directory))/'lifecycle.json')]
                child=subprocess.Popen(command,env=env,stdout=output,stderr=output,start_new_session=True)
                try:
                    while child.poll() is None:
                        sample=snapshot();samples.append(sample)
                        if violations(sample,policy):raise RuntimeError('Quiet/reserve guard interrupted CPU speech test')
                        if time.monotonic()-started>120:raise TimeoutError('CPU speech test expired')
                        if first_text_s is None and first.get_text():first_text_s=time.monotonic()-started
                        pump(.2)
                    if child.returncode:raise RuntimeError('CPU speech child failed: '+log.read_text()[-1000:])
                finally:
                    try:os.killpg(child.pid,signal.SIGTERM)
                    except ProcessLookupError:pass
                    try:child.wait(timeout=5)
                    except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
            actual=first.get_text();reference='He hoped there would be stew for dinner, turnips and carrots and bruised potatoes and fat mutton pieces to be ladled out in thick, peppered, flour-fattened sauce'
            expected_words=re.findall(r"\w+",reference.lower());words=re.findall(r"\w+",actual.lower())
            distances=list(range(len(words)+1))
            for i,left in enumerate(expected_words,1):
                row=[i]
                for j,right in enumerate(words,1):row.append(min(row[-1]+1,distances[j]+1,distances[j-1]+(left!=right)))
                distances=row
            wer=distances[-1]/len(expected_words)
            assert words and wer<=.1,(wer,actual)
            speech_receipt={'backend':'cpu','wav_sha256':hashlib.sha256(args.speech_file.read_bytes()).hexdigest(),
                'normalized_word_error_rate':wer,'widget_text':actual,'first_widget_text_s':first_text_s,
                'elapsed_s':time.monotonic()-started,'min_available_bytes':min(s['available_bytes'] for s in samples),
                'max_fan_rpm':max(max(s['fans_rpm'].values()) for s in samples),
                'max_temp_c':max(max(s['temperatures_c'].values()) for s in samples),
                'samples':len(samples),'quiet_policy_passed':True,'microphone_recorded':False}
        reconnect_receipt=None
        if args.reconnect_check:
            daemon.terminate();daemon.wait(timeout=5);pump()
            engine.wait(timeout=5)
            clean_disconnect=engine.returncode==0
            # The private daemon leaves its Unix socket pathname on TERM.
            # Remove only our socket after its owning process has exited.
            socket=Path(directory)/'bus'
            if socket.exists():socket.unlink()
            daemon=subprocess.Popen(['ibus-daemon','--single','--emoji-extension','disable',
                '--address',os.environ['IBUS_ADDRESS'],'--cache','none'])
            pump(1)
            engine=subprocess.Popen(['/usr/bin/python3',str(evaluated/'dictation-input.py')])
            pump(1)
            assert bus.is_connected(),'GTK/IBus bus did not reconnect'
            assert bus.get_global_engine() is None,'Fixture must exercise an unset global engine'
            assert run_client('repair-native').returncode==0
            assert bus.get_global_engine().get_name()=='xkb:us::eng'
            # Removing our dynamic component clears even the static engine.
            # Recreate only that private bridge to exercise Begin's fallback.
            engine.terminate();engine.wait(timeout=5);pump()
            assert bus.get_global_engine() is None
            engine=subprocess.Popen(['/usr/bin/python3',str(evaluated/'dictation-input.py')]);pump(1)
            result=run_client('begin');assert result.returncode==0,result.stderr
            recovered=result.stdout.strip()
            previous_text=first.get_text()
            assert run_client('commit',recovered,' recovered').returncode==0
            pump();assert first.get_text()==previous_text+' recovered'
            assert run_client('finish',recovered).returncode==0
            assert bus.get_global_engine().get_name()=='xkb:us::eng'
            reconnect_receipt={'private_ibus_restarted':True,'bridge_clean_disconnect':clean_disconnect,
                'unset_engine_recovered_from_native_source':True,'startup_native_repair':True,'gtk_client_reconnected':True}
        result=run_client('begin');assert result.returncode==0,result.stderr
        token=result.stdout.strip()
        second.grab_focus();pump()
        assert run_client('check',token).returncode!=0,'Pre-capture check accepted a changed field'
        assert run_client('commit',token,'wrong field').returncode!=0,'Focus change accepted stale insertion'
        assert not second.get_text()
        # A deliberate owner layout change during a lease must win over the
        # automatic restore, even when the token has already lost focus.
        assert bus.set_global_engine('xkb:fr::fra');pump()
        assert run_client('finish',token).returncode==0
        assert bus.get_global_engine().get_name()=='xkb:fr::fra','Finish overwrote owner selection'
        assert run_client('repair-native').returncode==0
        assert bus.get_global_engine().get_name()=='xkb:fr::fra','Startup repair overwrote a nonempty owner selection'
        password.grab_focus();pump()
        assert run_client('begin').returncode!=0,'Password accepted dictation'
        assert not password.get_text()
        assert bus.get_global_engine().get_name()=='xkb:fr::fra','Sensitive Begin changed input method'
        window.destroy();pump()
        receipt={'passed':True,'source_sha256':source_hashes,'gtk_version':4 if args.gtk4 else 3,'display_backend':'wayland' if args.wayland else 'x11','unicode_field':True,'changed_field_untouched':True,
            'password_untouched':True,'session_engine_restore':True,'overlapping_begin_refused':True,'owner_selection_preserved':True,'reconnect':reconnect_receipt,'speech':speech_receipt,'keyboard':keyboard_receipt,'method':'Actual Gtk.Entry fields, private '+('headless Gala Wayland' if args.wayland else 'Xvfb')+'/IBus/session bus; '+('CPU file ASR; no microphone' if speech_receipt else 'no ASR or microphone')}
        if args.receipt_dir:(args.receipt_dir/'receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
        print(json.dumps(receipt))
    finally:
        if engine:engine.terminate();engine.wait(timeout=5)
        daemon.terminate();daemon.wait(timeout=5)
