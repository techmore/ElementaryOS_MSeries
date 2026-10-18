#!/usr/bin/python3
"""Actual Qt6 fields on a private Xvfb/IBus bus; PyQt6 is a test dependency only."""
import ctypes
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

if os.environ.get('MSERIES_INPUT_TEST_SESSION') != '1':
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env',
        'MSERIES_INPUT_TEST_SESSION=1','GSETTINGS_BACKEND=memory',sys.executable,str(Path(__file__).resolve())]).returncode)

with tempfile.TemporaryDirectory(prefix='mseries-qt-input-') as directory:
    os.environ.update(IBUS_ADDRESS='unix:path='+directory+'/bus',QT_IM_MODULE='ibus',
        QT_QPA_PLATFORM='xcb',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1',GIO_USE_VFS='local',
        XDG_CACHE_HOME=directory+'/cache',XDG_CONFIG_HOME=directory+'/config')
    import gi
    gi.require_version('IBus','1.0')
    from gi.repository import IBus,GLib
    from PyQt6.QtWidgets import QApplication,QWidget,QVBoxLayout,QLineEdit,QTextEdit
    daemon=subprocess.Popen(['ibus-daemon','--single','--emoji-extension','disable',
        '--address',os.environ['IBUS_ADDRESS'],'--cache','none'])
    engine=None;app=None
    def pump(seconds=.3):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            if app:app.processEvents()
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            time.sleep(.01)
    try:
        time.sleep(1);IBus.init();bus=IBus.Bus.new();assert bus.is_connected()
        engine=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).with_name('dictation-input.py'))])
        pump(1);assert bus.set_global_engine('mseries-dictation')
        app=QApplication([]);window=QWidget();window.setWindowTitle('Synthetic Qt dictation fields')
        layout=QVBoxLayout(window);first,second,password=QLineEdit(),QLineEdit(),QLineEdit()
        password.setEchoMode(QLineEdit.EchoMode.Password);multiline=QTextEdit()
        for field in [first,second,password,multiline]:layout.addWidget(field)
        window.show();window.activateWindow();pump()
        x11=ctypes.CDLL('libX11.so.6');x11.XOpenDisplay.argtypes=[ctypes.c_char_p];x11.XOpenDisplay.restype=ctypes.c_void_p
        x11.XSetInputFocus.argtypes=[ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_ulong]
        x11.XFlush.argtypes=[ctypes.c_void_p];x11.XCloseDisplay.argtypes=[ctypes.c_void_p]
        display=x11.XOpenDisplay(None);assert display
        try:x11.XSetInputFocus(display,int(window.winId()),1,0);x11.XFlush(display)
        finally:x11.XCloseDisplay(display)
        first.setFocus();pump(1)
        client=['/usr/bin/python3',str(Path(__file__).with_name('dictation-input-client.py'))]
        def call(method,token=None,text=''):
            command=client+[method]+([token] if token else [])
            child=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            child.stdin.write(text);child.stdin.close();child.stdin=None
            deadline=time.monotonic()+5
            while child.poll() is None:
                if time.monotonic()>deadline:
                    child.kill();child.wait();raise TimeoutError('Bounded Qt client request expired')
                pump(.02)
            stdout,stderr=child.communicate()
            return subprocess.CompletedProcess(command,child.returncode,stdout,stderr)
        result=call('begin');assert result.returncode==0,result.stderr;token=result.stdout.strip()
        text='Café — 日本語 + & $(literal)'
        for chunk in [text[:8],text[8:]]:
            result=call('commit',token,chunk);assert result.returncode==0,result.stderr;pump()
        assert first.text()==text,repr(first.text())
        second.setFocus();pump();assert call('commit',token,'wrong field').returncode!=0
        assert not second.text()
        password.setFocus();pump();assert call('begin').returncode!=0;assert not password.text()
        multiline.setFocus();pump();result=call('begin');assert result.returncode==0,result.stderr
        result=call('commit',result.stdout.strip(),'Line one\n日本語 & café');assert result.returncode==0,result.stderr;pump()
        assert multiline.toPlainText()=='Line one\n日本語 & café'
        window.close();pump()
        print(json.dumps({'qt6_unicode_field':True,'qt6_multiline':True,'changed_field_untouched':True,
            'password_untouched':True,'method':'Real Qt6 X11 widgets in private Xvfb/IBus/session bus; no microphone or ASR'}))
    finally:
        if engine:engine.terminate();engine.wait(timeout=5)
        daemon.terminate();daemon.wait(timeout=5)
