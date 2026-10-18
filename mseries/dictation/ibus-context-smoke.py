#!/usr/bin/python3
"""Run under dbus-run-session -- xvfb-run -a; never uses the owner IBus bus."""
import os,subprocess,tempfile,time,json
from pathlib import Path
import gi
gi.require_version('IBus','1.0')
from gi.repository import IBus,Gio,GLib
script=Path(__file__).resolve().with_name('dictation-input.py')
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
  received=[]
  def committed(connection,sender,path,interface,signal,parameters):
   received.append(parameters.unpack()[0][2])
  bus.get_connection().signal_subscribe(None,'org.freedesktop.IBus.InputContext','CommitText',ctx.get_object_path(),None,Gio.DBusSignalFlags.NONE,committed)
  conn=Gio.bus_get_sync(Gio.BusType.SESSION,None)
  def call(method,args=None):return conn.call_sync('org.techmore.DictationInput','/org/techmore/DictationInput','org.techmore.DictationInput',method,args,None,Gio.DBusCallFlags.NONE,2000,None)
  token=call('Begin').unpack()[0]
  text='Café — 日本語 + & $(literal)'
  call('Commit',GLib.Variant('(ss)',(token,text)));pump();assert received==[text],received
  ctx.focus_out();pump()
  try:call('Commit',GLib.Variant('(ss)',(token,'wrong field')))
  except GLib.Error:pass
  else:raise AssertionError('Focus-out accepted stale token')
  ctx.focus_in();ctx.set_content_type(IBus.InputPurpose.PASSWORD,IBus.InputHints.NONE);pump()
  try:call('Begin')
  except GLib.Error:pass
  else:raise AssertionError('Password accepted')
  print(json.dumps({'unicode_commit':True,'focus_out_rejected':True,'password_rejected':True,'method':'Isolated real IBus InputContext; no owner desktop or microphone'}))
 finally:
  if engine:engine.terminate();engine.wait(timeout=5)
  daemon.terminate();daemon.wait(timeout=5)
