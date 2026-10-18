#!/usr/bin/python3
"""Run under dbus-run-session -- xvfb-run -a; never uses the owner IBus bus."""
import os,subprocess,tempfile,time,json,sys
from pathlib import Path
import gi
gi.require_version('IBus','1.0')
from gi.repository import IBus,Gio,GLib
script=Path(__file__).resolve().with_name('dictation-input.py')
if os.environ.get('MSERIES_INPUT_TEST_SESSION') != '1':
 raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env','MSERIES_INPUT_TEST_SESSION=1',
  'GSETTINGS_BACKEND=memory',sys.executable,str(Path(__file__).resolve())]).returncode)
with tempfile.TemporaryDirectory(prefix='mseries-ibus-') as d:
 os.environ['IBUS_ADDRESS']='unix:path='+d+'/bus'
 os.environ['GIO_USE_VFS']='local'
 os.environ['XDG_CACHE_HOME']=d+'/cache';os.environ['XDG_CONFIG_HOME']=d+'/config'
 daemon=subprocess.Popen(['ibus-daemon','--single','--emoji-extension','disable','--address',os.environ['IBUS_ADDRESS'],'--cache','none'])
 engine=None
 def pump(seconds=.2):
  until=time.monotonic()+seconds
  while time.monotonic()<until:
   while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
   time.sleep(.01)
 try:
  time.sleep(1);IBus.init();bus=IBus.Bus.new();assert bus.is_connected()
  engine=subprocess.Popen(['/usr/bin/python3',str(script)])
  pump(1)
  ctx=bus.create_input_context('gtk3-im:synthetic-dictation-test')
  ctx.set_capabilities(IBus.Capabilite.FOCUS);ctx.focus_in();assert bus.set_global_engine('mseries-dictation');pump(1)
  assert ctx.get_engine().get_name()=='mseries-dictation'; ctx.focus_out();pump();ctx.focus_in();pump();ctx.set_content_type(IBus.InputPurpose.FREE_FORM,IBus.InputHints.NONE);pump()
  conn=Gio.bus_get_sync(Gio.BusType.SESSION,None)
  def call(method,args=None):return conn.call_sync('org.techmore.DictationInput','/org/techmore/DictationInput','org.techmore.DictationInput',method,args,None,Gio.DBusCallFlags.NONE,2000,None)
  try:call('Begin')
  except GLib.Error as error:assert 'metadata' in str(error),str(error)
  else:raise AssertionError('Unbacked input context accepted without accessible field')
  ctx.focus_out();pump()
  try:call('Begin')
  except GLib.Error:pass
  else:raise AssertionError('Unfocused context accepted')
  print(json.dumps({'unbacked_context_refused':True,'unfocused_context_refused':True,
    'method':'Isolated real IBus InputContext without accessible application; no text or microphone'}))

 finally:
  if engine:engine.terminate();engine.wait(timeout=5)
  daemon.terminate();daemon.wait(timeout=5)
