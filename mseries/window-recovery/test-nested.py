#!/usr/bin/python3
"""Run under dbus-run-session; Xvfb isolates every pointer/key and dock process."""
import os, subprocess as sp, tempfile, time, re, json
from pathlib import Path
from gi.repository import Gio, GLib
root=Path(__file__).resolve().parents[2]
scratch=tempfile.TemporaryDirectory(prefix='pantheon-snap-smoke-')
work=Path(scratch.name)
env=os.environ.copy()
for k in ['WAYLAND_DISPLAY','WAYLAND_SOCKET','DISPLAY','SESSION_MANAGER']:
    env.pop(k,None)
env.update(XDG_RUNTIME_DIR=tempfile.mkdtemp(prefix='runtime-',dir=work),XDG_CONFIG_HOME=tempfile.mkdtemp(prefix='config-',dir=work),GSETTINGS_BACKEND='memory',WINIT_UNIX_BACKEND='x11',PANTHEON_WAYLAND_DISPLAY='snap-smoke',LIBGL_ALWAYS_SOFTWARE='1',GSK_RENDERER='gl',RUST_LOG='info',GTK_A11Y='none',GTK_USE_PORTAL='0')
os.chmod(env['XDG_RUNTIME_DIR'],0o700)
procs=[]
def launch(args, e=env, name='process'):
    out=(work/(name+'.log')).open('w')
    p=sp.Popen(args,env=e,stdout=out,stderr=sp.STDOUT);procs.append(p);return p

def waitfor(fn, timeout=12):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        try:
            result=fn()
            if result:return result
        except (Exception,):pass
        time.sleep(.1)
    raise AssertionError('timed out waiting for '+str(fn))

def cmd(args,e=env):return sp.check_output(args,env=e,text=True).strip()

def call(method,params=None):
    return Gio.bus_get_sync(Gio.BusType.SESSION,None).call_sync('org.pantheon.gala','/org/pantheon/gala/DesktopInterface','org.pantheon.gala.DesktopIntegration',method,params,None,Gio.DBusCallFlags.NONE,3000,None).unpack()
def windows():return call('GetWindows')[0]
def focused(uid):return any(i==uid and p['has-focus'] for i,p in windows())
def action(n):
    Gio.bus_get_sync(Gio.BusType.SESSION,None).call_sync('org.pantheon.gala','/org/pantheon/gala','org.pantheon.gala','PerformAction',GLib.Variant('(i)',(n,)),None,Gio.DBusCallFlags.NONE,3000,None)
try:
    xv=sp.Popen(['Xvfb','-displayfd','1','-screen','0','1280x900x24','-nolisten','tcp'],stdout=sp.PIPE,stderr=(work/'xvfb.log').open('w'),text=True);procs.append(xv)
    env['DISPLAY']=':'+xv.stdout.readline().strip()
    launch([str(root/'rust/target/debug/pantheon-compositor')],name='compositor')
    waitfor(lambda:'XWayland is ready' in (work/'compositor.log').read_text())
    log=(work/'compositor.log').read_text()
    inner=re.search(r'display_number[=\x1b\[0-9m ]+(\d+)',re.sub(r'\x1b\[[0-9;]*m','',log)).group(1)
    xenv=env|{'DISPLAY':':'+inner,'GDK_BACKEND':'x11','WAYLAND_DISPLAY':'snap-smoke'}
    entry_code = """import gi,os
from pathlib import Path
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
window=Gtk.Window(title='SnapRecoverySmoke')
window.set_default_size(320,200)
entry=Gtk.Entry()
entry.connect('changed', lambda item: Path(os.environ['SMOKE_TYPED_FILE']).write_text(item.get_text()))
window.set_child(entry)
window.present()
entry.grab_focus()
def allocation():
    if 'SMOKE_SIZE_FILE' in os.environ:
        Path(os.environ['SMOKE_SIZE_FILE']).write_text(str(window.get_width()))
    return True
GLib.timeout_add(100, allocation)
loop=GLib.MainLoop()
window.connect('close-request',lambda *_:loop.quit())
loop.run()
"""
    xenv['SMOKE_TYPED_FILE']=str(work/'typed')
    launch(['python3','-c',entry_code],xenv,'entry')
    uid=waitfor(lambda:windows())[0][0]
    wid=waitfor(lambda:cmd(['xdotool','search','--name','SnapRecoverySmoke'],xenv).splitlines()[0])
    outer=cmd(['xdotool','search','--onlyvisible','--name','Smithay']).splitlines()[0]
    cmd(['xdotool','windowfocus',outer])
    cmd(['xdotool','key','--clearmodifiers','ctrl+super+Left'])
    def geom():
        return dict(line.split('=') for line in cmd(['xdotool','getwindowgeometry','--shell',wid],xenv).splitlines())
    left=waitfor(lambda: (g if int(g['X'])==0 and int(g['WIDTH'])>350 else None) if (g:=geom()) else None)
    cmd(['xdotool','key','--clearmodifiers','ctrl+super+Right'])
    right=waitfor(lambda:(g if int(g['X'])>300 else None) if (g:=geom()) else None)
    action(3)
    waitfor(lambda:not focused(uid))
    sp.run(['python3',str(root/'mseries/window-recovery/restore-windows.py'),'--focus',str(uid)],env=xenv,check=True)
    waitfor(lambda:focused(uid))
    dockenv=env|{'WAYLAND_DISPLAY':'snap-smoke','GDK_BACKEND':'wayland'}
    dock_binary=os.environ.get('MSERIES_SMOKE_DOCK','/usr/bin/io.elementary.dock')
    if 'MSERIES_SMOKE_DOCK' in os.environ:
        dockenv['GSETTINGS_SCHEMA_DIR']=str(Path(dock_binary).parent.parent/'share/glib-2.0/schemas')
    dock=launch([dock_binary],dockenv,'dock')
    waitfor(lambda:'first Pantheon panel buffer committed' in (work/'compositor.log').read_text())
    assert focused(uid),'dock startup stole focus'
    launch([dock_binary],dockenv,'dock-repeat')
    time.sleep(.5)
    assert focused(uid),'dock repeat activation stole focus'
    cmd(['xdotool','type','--clearmodifiers','typing-still-works'])
    waitfor(lambda:(work/'typed').exists() and (work/'typed').read_text()=='typing-still-works')
    nativeenv=dockenv|{'SMOKE_TYPED_FILE':str(work/'native-typed'),'SMOKE_SIZE_FILE':str(work/'native-size')}
    native_code=entry_code.replace('SnapRecoverySmoke','NativeSnapSmoke')
    launch(['python3','-c',native_code],nativeenv,'native-entry')
    native_uid=waitfor(lambda:next(((i,) for i,p in windows() if p.get('title')=='NativeSnapSmoke'),None))[0]
    waitfor(lambda:focused(native_uid))
    cmd(['xdotool','key','--clearmodifiers','ctrl+super+Left'])
    waitfor(lambda:(work/'native-size').exists() and int((work/'native-size').read_text())==640)
    action(3)
    waitfor(lambda:not focused(native_uid))
    sp.run(['python3',str(root/'mseries/window-recovery/restore-windows.py'),'--focus',str(native_uid)],env=nativeenv,check=True)
    waitfor(lambda:focused(native_uid))
    cmd(['xdotool','type','--clearmodifiers','native-typing-works'])
    waitfor(lambda:(work/'native-typed').exists() and (work/'native-typed').read_text()=='native-typing-works')
    print(json.dumps({'native_snap_and_restore':True,'x11_left':left,'x11_right':right,'minimize_restore':True,'typing_after_dock_activation':True,'dock_first_buffer_preserves_focus':True,'dock_repeat_preserves_focus':True},indent=2))
except Exception:
    for name in ['compositor','entry','dock','native-entry']:
        log=work/(name+'.log')
        if log.exists(): print(name,log.read_text()[-3500:])
    print('windows at failure',windows())
    raise
finally:
    for p in reversed(procs):
        if p.poll() is None:p.terminate()
    for p in reversed(procs):
        try:p.wait(timeout=4)
        except sp.TimeoutExpired:p.kill()
