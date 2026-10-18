#!/usr/bin/python3
"""Synthetic GTK fields on a private IBus/Xvfb session; no microphone or global keys.
Run: dbus-run-session -- xvfb-run -a python3 mseries/dictation/gtk-input-smoke.py
"""
import json
import argparse
import os
from pathlib import Path
import subprocess
import tempfile
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--gtk4',action='store_true')
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='mseries-gtk-input-') as directory:
    os.environ.update(IBUS_ADDRESS='unix:path='+directory+'/bus', GTK_IM_MODULE='ibus',
        GDK_BACKEND='x11', XDG_CACHE_HOME=directory+'/cache', XDG_CONFIG_HOME=directory+'/config',
        NO_AT_BRIDGE='1', GIO_USE_VFS='local',GSK_RENDERER='cairo',LIBGL_ALWAYS_SOFTWARE='1')
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
        token=subprocess.run(client+['begin'],capture_output=True,text=True,check=True).stdout.strip()
        text='Café — 日本語 + & $(literal)'
        for chunk in [text[:8],text[8:]]:
            subprocess.run(client+['commit',token],input=chunk,text=True,capture_output=True,check=True);pump()
        assert first.get_text()==text,first.get_text()
        second.grab_focus();pump()
        try:call('Commit',GLib.Variant('(ss)',(token,'wrong field')))
        except GLib.Error:pass
        else:raise AssertionError('Focus change accepted stale insertion')
        assert not second.get_text()
        password.grab_focus();pump()
        try:call('Begin')
        except GLib.Error:pass
        else:raise AssertionError('Password accepted dictation')
        assert not password.get_text()
        window.destroy();pump()
        print(json.dumps({'gtk_version':4 if args.gtk4 else 3,'unicode_field':True,'changed_field_untouched':True,
            'password_untouched':True,'method':'Actual Gtk.Entry fields, private Xvfb/IBus/session bus; no ASR or microphone'}))
    finally:
        if engine:engine.terminate();engine.wait(timeout=5)
        daemon.terminate();daemon.wait(timeout=5)
