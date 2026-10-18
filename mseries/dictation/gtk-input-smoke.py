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

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gtk4',action='store_true')
parser.add_argument('--wayland',action='store_true',help='Use only inside an isolated nested Wayland desktop')
args=parser.parse_args()
if args.wayland:
    assert os.environ.get('MSERIES_DICTATION_TEST_BUS') == '1' and os.environ.get('GSETTINGS_BACKEND') == 'memory', 'Use test-wayland-input.sh'
elif os.environ.get('MSERIES_INPUT_TEST_SESSION') != '1':
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env',
        'MSERIES_INPUT_TEST_SESSION=1','GSETTINGS_BACKEND=memory',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]]).returncode)
with tempfile.TemporaryDirectory(prefix='mseries-gtk-input-') as directory:
    os.environ.update(IBUS_ADDRESS='unix:path='+directory+'/bus', GTK_IM_MODULE='ibus',
        GDK_BACKEND='wayland' if args.wayland else 'x11', XDG_CACHE_HOME=directory+'/cache', XDG_CONFIG_HOME=directory+'/config',
        GTK_A11Y='atspi', GIO_USE_VFS='local',GSK_RENDERER='cairo',LIBGL_ALWAYS_SOFTWARE='1')
    import gi
    gi.require_version('IBus','1.0')
    gi.require_version('Gtk','4.0' if args.gtk4 else '3.0')
    gi.require_version('Gdk','4.0' if args.gtk4 else '3.0')
    from gi.repository import IBus,Gio,GLib,Gtk,Gdk
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
        engine=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).with_name('dictation-input.py'))])
        pump(1);assert bus.set_global_engine('mseries-dictation')
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
        conn=Gio.bus_get_sync(Gio.BusType.SESSION,None)
        def call(method,args=None):
            return conn.call_sync('org.techmore.DictationInput','/org/techmore/DictationInput',
                'org.techmore.DictationInput',method,args,None,Gio.DBusCallFlags.NONE,2000,None)
        client=['/usr/bin/python3',str(Path(__file__).with_name('dictation-input-client.py'))]
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
        text='Café — 日本語 + & $(literal)'
        for chunk in [text[:8],text[8:]]:
            result=run_client('commit',token,chunk);assert result.returncode==0,result.stderr
            pump()
        assert first.get_text()==text,first.get_text()
        second.grab_focus();pump()
        assert run_client('commit',token,'wrong field').returncode!=0,'Focus change accepted stale insertion'
        assert not second.get_text()
        password.grab_focus();pump()
        assert run_client('begin').returncode!=0,'Password accepted dictation'
        assert not password.get_text()
        window.destroy();pump()
        print(json.dumps({'gtk_version':4 if args.gtk4 else 3,'display_backend':'wayland' if args.wayland else 'x11','unicode_field':True,'changed_field_untouched':True,
            'password_untouched':True,'method':'Actual Gtk.Entry fields, private '+('headless Gala Wayland' if args.wayland else 'Xvfb')+'/IBus/session bus; no ASR or microphone'}))
    finally:
        if engine:engine.terminate();engine.wait(timeout=5)
        daemon.terminate();daemon.wait(timeout=5)
