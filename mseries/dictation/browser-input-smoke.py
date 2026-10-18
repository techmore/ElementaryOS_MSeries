#!/usr/bin/python3
"""Actual Brave form insertion on a private Xvfb/IBus bus, GPU disabled.
Run: dbus-run-session -- xvfb-run -a python3 mseries/dictation/browser-input-smoke.py
"""
import json
import argparse
import os
from pathlib import Path
import signal
import sys
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from websockets.sync.client import connect
import gi
gi.require_version('IBus','1.0')
from gi.repository import IBus,Gio,GLib

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--automatic-accessibility',action='store_true')
parser.add_argument('--enable-accessibility-status',action='store_true',help='Enable accessibility only on the private test bus')
parser.add_argument('--electron',type=Path,help='Unpackaged Electron executable for a synthetic form')
args=parser.parse_args()

if os.environ.get('MSERIES_INPUT_TEST_SESSION') != '1':
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env','MSERIES_INPUT_TEST_SESSION=1',
        'GSETTINGS_BACKEND=memory',sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]]).returncode)

with tempfile.TemporaryDirectory(prefix='mseries-browser-input-') as directory:
    os.environ.update(IBUS_ADDRESS='unix:path='+directory+'/bus',XMODIFIERS='@im=ibus',
        GTK_IM_MODULE='ibus',GDK_BACKEND='x11',GIO_USE_VFS='local',
        XDG_CACHE_HOME=directory+'/cache',XDG_CONFIG_HOME=directory+'/config')
    daemon=subprocess.Popen(['ibus-daemon','--single','--xim','--emoji-extension','disable',
        '--address',os.environ['IBUS_ADDRESS'],'--cache','none'])
    engine=browser=None
    def pump(seconds=.3):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            time.sleep(.01)
    try:
        time.sleep(1);IBus.init();bus=IBus.Bus.new();assert bus.is_connected()
        engine=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).with_name('dictation-input.py'))])
        pump(1);assert bus.set_global_engine('mseries-dictation')
        if args.enable_accessibility_status:
            connection=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            connection.call_sync('org.a11y.Bus','/org/a11y/bus','org.freedesktop.DBus.Properties','Set',
                GLib.Variant('(ssv)',('org.a11y.Status','IsEnabled',GLib.Variant('b',True))),None,Gio.DBusCallFlags.NONE,3000,None)
        profile=Path(directory)/'profile'
        executable=['brave-browser']
        if args.electron:
            bootstrap=Path(directory)/'fixture.cjs'
            bootstrap.write_text("const {app,BrowserWindow}=require('electron'); app.whenReady().then(()=>{ const window=new BrowserWindow({show:true,webPreferences:{sandbox:true,nodeIntegration:false,contextIsolation:true}}); window.loadURL('about:blank'); });")
            executable=[str(args.electron.resolve()),str(bootstrap)]
        flags=['--user-data-dir='+str(profile),'--ozone-platform=x11','--disable-gpu','--disable-background-networking',
            '--disable-extensions','--disable-sync','--no-first-run','--no-default-browser-check',
            '--password-store=basic','--remote-debugging-address=127.0.0.1',
            '--remote-debugging-port=0','--host-resolver-rules=MAP * ~NOTFOUND']
        if not args.automatic_accessibility:flags.append('--force-renderer-accessibility')
        browser=subprocess.Popen(executable+flags+([] if args.electron else ['about:blank']),
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)

        for _ in range(100):
            if (profile/'DevToolsActivePort').exists():break
            if browser.poll() is not None:raise RuntimeError('Owned browser exited')
            time.sleep(.1)
        port=int((profile/'DevToolsActivePort').read_text().splitlines()[0])
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list',timeout=3) as response:tabs=json.load(response)
        tab=next(t for t in tabs if t['type']=='page')
        with connect(tab['webSocketDebuggerUrl'],proxy=None,open_timeout=3) as ws:
            seq=0
            def cdp(method,params=None):
                global seq
                seq+=1;ws.send(json.dumps({'id':seq,'method':method,'params':params or {}}))
                while True:
                    result=json.loads(ws.recv(timeout=5))
                    if result.get('id')==seq:
                        if 'error' in result:raise RuntimeError(result['error'])
                        return result.get('result',{})
            def js(expression):return cdp('Runtime.evaluate',{'expression':expression,'returnByValue':True})['result'].get('value')
            html='<meta charset="utf-8"><input id="first"><input id="second"><input id="password" type="password">'
            cdp('Page.navigate',{'url':'data:text/html,'+urllib.parse.quote(html)});pump(1)
            cdp('Page.bringToFront');js('document.querySelector("#first").focus()');pump(1)
            conn=Gio.bus_get_sync(Gio.BusType.SESSION,None)
            def call(method,args=None):return conn.call_sync('org.techmore.DictationInput','/org/techmore/DictationInput',
                'org.techmore.DictationInput',method,args,None,Gio.DBusCallFlags.NONE,2000,None)
            token=call('Begin').unpack()[0];text='Café — 日本語 + & $(literal)'
            call('Commit',GLib.Variant('(ss)',(token,text)));pump()
            actual=js('document.querySelector("#first").value');assert actual==text,repr(actual)
            js('document.querySelector("#second").focus()');pump()
            try:call('Commit',GLib.Variant('(ss)',(token,'wrong field')))
            except GLib.Error:pass
            else:raise AssertionError('Browser field change accepted stale insertion')
            assert js('document.querySelector("#second").value')==''
            js('document.querySelector("#password").focus()');pump()
            try:call('Begin')
            except GLib.Error:pass
            else:raise AssertionError('Browser password accepted dictation')
            print(json.dumps({'browser':'Electron synthetic X11' if args.electron else 'Brave X11','accessibility':'automatic with OS support enabled' if args.enable_accessibility_status else ('automatic' if args.automatic_accessibility else 'forced'),'unicode_field':True,'changed_field_untouched':True,
                'password_refused':True,'method':'Synthetic form in isolated real browser; no ASR, microphone or owner profile'}))
    finally:
        if browser:
            try:os.killpg(browser.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:browser.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(browser.pid,signal.SIGKILL);browser.wait()
            # Chromium's parent can exit before its profile-writing children.
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                try:os.killpg(browser.pid,0)
                except ProcessLookupError:break
                time.sleep(.05)
            try:os.killpg(browser.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            time.sleep(.1)
        if engine:engine.terminate();engine.wait(timeout=5)
        daemon.terminate();daemon.wait(timeout=5)
