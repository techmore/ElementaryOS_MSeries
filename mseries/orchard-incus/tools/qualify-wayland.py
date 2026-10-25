#!/usr/bin/env python3
"""Opt-in real Wayland/Incus qualification; uses uniquely owned disposable guests.
Programmatic native GTK actions, not physical input automation. Native save portals use AT-SPI; a one-shot guest profile verifies Terminal.
Interactive keyboard input, upload-picker selection and interactive Console
are not automated. Requires cached Alpine container/VM images and Wayland.
"""
import argparse, concurrent.futures, gc, json, os, pathlib, resource, shlex, socket, subprocess, sys, time, traceback, uuid
from audit_scope import AuditScope
from frame_metrics import summarize_frames
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',required=True);p.add_argument('--output',required=True);p.add_argument('--run',action='store_true')
p.add_argument('--cycles',type=int,default=1)
p.add_argument('--idle-before',type=int,default=0,help='Seconds of idle observation before workflows')
p.add_argument('--idle-after',type=int,default=0,help='Seconds of idle observation after workflows')
p.add_argument('--cycle-interval',type=int,default=0,help='Minimum seconds between workflow-cycle starts; observe idle between cycles')
p.add_argument('--session-seconds',type=int,default=0,help='Minimum total observation duration, including cycles and idle')
a=p.parse_args()
if not 1 <= a.cycles <= 20 or min(a.idle_before,a.idle_after,a.cycle_interval,a.session_seconds)<0: p.error('Use 1–20 cycles and nonnegative durations')
if not a.run: p.error('--run is required: creates and deletes owned disposable Incus instances')
sys.path.insert(0,a.source)
from orchard_incus.app import App
from orchard_incus import backend
import orchard_incus.window as module
from gi.repository import Gtk,Gdk,GLib,Graphene
Gtk.init()
if type(Gdk.Display.get_default()).__name__!='GdkWaylandDisplay':
 p.error('A native Wayland display is required; run with GDK_BACKEND=wayland. No guests were changed.')
out=pathlib.Path(a.output).resolve()
if out.exists() and (not out.is_dir() or any(out.iterdir())):
 p.error('Use a new, empty output directory for each audit run')
out.mkdir(parents=True,exist_ok=True)
module.STATE_FILE=str(out/'window-state.json')
prefix='oi-wayland-'+uuid.uuid4().hex[:8];name=prefix+'-dev';clone=prefix+'-copy';renamed=prefix+'-renamed'
vm_name=prefix+'-vm';cancel_name=prefix+'-cancel';owned={name,clone,renamed,vm_name,cancel_name};(out/'owned.json').write_text(json.dumps(sorted(owned)));pool=concurrent.futures.ThreadPoolExecutor(max_workers=2)
initial={x['name']:x['status'] for x in backend.ijson('list')}
if owned & initial.keys():raise RuntimeError('Audit fixture name collision; no instances changed')
created_tokens=set()
images=backend.ijson('image','list');image=next(x['fingerprint'] for x in images if x.get('type')=='container' and 'Alpine' in x.get('properties',{}).get('description',''))
app=App();app.set_application_id('io.github.techmore.OrchardWaylandAudit.T'+uuid.uuid4().hex);app.register(None)
win=module.Window(app);win.set_title('Orchard — session audit: '+out.name);win.present()
loop=GLib.MainLoop();errors=[];expected_errors=[];results=[];pending=None;phase_iter=None;phase_name='';frame_refs=[];actions=[];frame_handler=0;tick_id=0;heartbeat=[];last_beat=time.monotonic();phase_start=0
report={'source_sha256':{x.name:__import__('hashlib').sha256(x.read_bytes()).hexdigest() for x in pathlib.Path(module.__file__).parent.glob('*.py')},'prefix':prefix,'source':a.source,'workflow_driver':'programmatic native GTK widget actions + independent Incus CLI assertions','results':results}
original_create=win.start_create
def guarded_create(n,image,extra):
 expected=backend.create_args(n==vm_name,'1','1GiB' if n==vm_name else '256MiB',secure_boot=False)
 if n not in owned or image not in {x['fingerprint'] for x in images} or extra!=expected:
  errors.append({'what':'audit fixture guard','error':'creation rejected outside exact owned names/images/limits'});return
 result=original_create(n,image,extra)
 if n in win.jobs:created_tokens.add(win.jobs[n]['token'])
 return result
win.start_create=guarded_create
original_incus=backend.incus
scope=AuditScope(owned,out)
def guarded_incus(*args, **kwargs):
 scope.check(args)
 return original_incus(*args, **kwargs)
backend.incus=guarded_incus
original_popen=subprocess.Popen
def guarded_popen(command,*args,**kwargs):
 if isinstance(command,(list,tuple)) and command:
  command=list(command)
  if command[:2]==['incus','exec']:
   scope.guest(command[2])
  elif command[:2]==['incus','launch']:
   scope.guest(command[3])
  elif pathlib.Path(command[0]).name==module.TERMINAL and '-e' in command:
   terminal=shlex.split(command[command.index('-e')+1])
   if len(terminal)<3 or terminal[:2] not in (['incus','exec'],['incus','console']):
    raise RuntimeError('Audit rejected an unrecognized Terminal command')
   scope.guest(terminal[2])
 return original_popen(command,*args,**kwargs)
subprocess.Popen=guarded_popen
original_error=win.error_dialog

def error(what,err):
 expected=phase_name=='duplicate-name-preserves-existing-guest' and 'already exists' in str(err).lower()
 (expected_errors if expected else errors).append({'what':what,'error':str(err)})
 print('EXPECTED UI ERROR' if expected else 'UI ERROR',what,str(err),flush=True)
 original_error(what,err)
 dialogs=[x for x in Gtk.Window.get_toplevels() if x and x is not win and x.get_transient_for() is win and isinstance(x,Gtk.Dialog)]
 def close_errors():
  for x in dialogs:
   if x.get_visible():x.response(Gtk.ResponseType.CLOSE)
  return False
 GLib.timeout_add(350,close_errors)
win.error_dialog=error

def walk(w):
 yield w
 c=w.get_first_child()
 while c:
  yield from walk(c);c=c.get_next_sibling()

def dialog(title=None):
 return next(x for x in Gtk.Window.get_toplevels() if x and x is not win and x.get_visible() and (title is None or x.get_title()==title))
def accept(d, expected=None):
 d.set_focus(None)
 yield from wait(d.get_mapped,'Dialog mapped')
 until=time.monotonic()+.25
 yield from wait(lambda:time.monotonic()>until,'Dialog frame settled')

 if expected is not None:
  entries=[x for x in walk(d) if isinstance(x,Gtk.Entry)]
  entries[0].set_text(expected)
 if d.get_title()=='New Instance':
  grid=next(x for x in walk(d) if isinstance(x,Gtk.Grid))
  print('FORM', [(r,grid.get_child_at(1,r).get_text()) for r in (0,2,5,6)], 'enabled', d.get_widget_for_response(Gtk.ResponseType.ACCEPT).get_sensitive(),flush=True)
 d.response(Gtk.ResponseType.ACCEPT)
def wait(fn,label,timeout=45):
 yield (fn,label,timeout)
def cli(*args,timeout=40):
 f=pool.submit(backend.incus,*args,timeout=timeout)
 yield from wait(f.done,'CLI '+args[0],timeout+2)
 return f.result()
def query(*args):
 text=yield from cli(*args,'--format','json')
 return json.loads(text)
def textbuffer(b):return b.get_text(b.get_start_iter(),b.get_end_iter(),False)
def select(n=None):
 if n is None:n=name
 win.refresh();yield from wait(lambda:n in win.data,'inventory contains owned guest')
 win.open_instance(n);yield from wait(lambda:win.cur==n,'select guest')
def state(verb,target=None,expected=None):
 if target is None:target=name
 yield from select(target);win.act(verb)
 yield from wait(lambda:target not in win.busy,'lifecycle '+verb,75)
 win.refresh()
 if expected:yield from wait(lambda:win.data.get(target,{}).get('status')==expected,'state '+expected)
def assert_eq(x,y):
 if x!=y:raise AssertionError(f'{x!r} != {y!r}')

def creation():
 yield from wait(lambda:win.ok and not win._checking,'Incus preflight')
 assert type(win.get_display()).__name__=='GdkWaylandDisplay'
 report['desktop']={'display':type(win.get_display()).__name__,'renderer':type(win.get_renderer()).__name__,'theme':Gtk.Settings.get_default().props.gtk_theme_name,'surface':type(win.get_surface()).__name__}
 win.on_new();d=dialog('New Instance');grid=next(x for x in walk(d) if isinstance(x,Gtk.Grid))
 grid.get_child_at(1,0).set_text(name);grid.get_child_at(1,1).set_selected(len(backend.PRESETS)-1);grid.get_child_at(1,2).set_text(image);grid.get_child_at(1,5).set_text('1');grid.get_child_at(1,6).set_text('256MiB');yield from accept(d,name)
 yield from wait(lambda:name not in win.jobs,'create job completion',90)
 yield from select()
 yield from wait(lambda:win.data[name]['status']=='Running','created guest running')
 win.search.set_text(prefix);win.filter_instances()

def duplicate_name():
 yield from select()
 before=json.loads((yield from cli('query','/1.0/instances/'+name)))
 original=before['config'][backend.CREATION_TOKEN_KEY]
 win.start_create(name,image,backend.create_args(False,'1','256MiB'))
 assert name not in win.jobs
 # Simulate a stale inventory: the backend already has the guest, but the
 # current GUI snapshot does not. The new failed job must not delete it.
 win.data.pop(name)
 win.start_create(name,image,backend.create_args(False,'1','256MiB'))
 yield from wait(lambda:name not in win.jobs,'Duplicate creation rejected by daemon')
 until=time.monotonic()+1
 yield from wait(lambda:time.monotonic()>until,'Ownership cleanup settles')
 after=json.loads((yield from cli('query','/1.0/instances/'+name)))
 assert_eq(after['config'][backend.CREATION_TOKEN_KEY],original)
 assert_eq(after['status'],'Running')
 assert expected_errors
 report['duplicate_name_preserved_original']=True
 win.refresh()

def run_and_files():
 yield from select();win.tabs.set_visible_child_name('ex')
 win.cmd.set_text("printf 'version-one\\n' >/root/orchard-audit.txt; printf 'ORCHARD_RUN_OK λ\\n'");win.run_cmd()
 yield from wait(lambda:name not in win.exec_proc,'Run command completed')
 assert 'ORCHARD_RUN_OK λ' in textbuffer(win.exec_buf(name))
 win.cmd.set_text("yes ORCHARD_OUTPUT | head -c 2000000; printf '\\nORCHARD_UNICODE_✓\\n'");win.run_cmd()
 yield from wait(lambda:name not in win.exec_proc,'Bounded guest output')
 assert win.exec_buf(name).get_char_count()<=262144
 assert 'ORCHARD_UNICODE_✓' in textbuffer(win.exec_buf(name))
 win.tabs.set_visible_child_name('fi');win.go_path('/root')
 yield from wait(lambda:any(getattr(x,'fname','')=='orchard-audit.txt' for x in walk(win.flist)),'Files lists command-created file')
 data=yield from cli('exec',name,'--','cat','/root/orchard-audit.txt');assert_eq(data.strip(),'version-one')
 # Independent transfer assertion, using only an audit-owned host path.
 source=out/'upload.txt';source.write_text('ORCHARD_TRANSFER_✓\n')
 yield from cli('file','push',str(source),name+'/root/upload.txt')
 yield from cli('file','pull',name+'/root/upload.txt',str(out/'download.txt'))
 assert_eq((out/'download.txt').read_text(),source.read_text())

def settings():
 yield from select();win.tabs.set_visible_child_name('se')
 yield from wait(lambda:win.settings_owner==name,'Settings loaded')
 assert_eq(win.set_cpu.get_text(),'1');win.set_cpu.set_text('2');win.set_mem.set_text('384MiB');win.settings_apply.emit('clicked')
 yield from wait(lambda:win.settings_owner==name and win.set_cpu.get_text()=='2' and name not in win.settings_pending,'Settings apply callback')
 # Wait for the read-back, independently of editable controls.
 def applied():
  task=win.reads.get('tab');return task is not None and not task.running
 yield from wait(applied,'Settings readback')
 cpu=yield from cli('config','get',name,'limits.cpu');mem=yield from cli('config','get',name,'limits.memory')
 assert_eq(cpu.strip(),'2');assert_eq(mem.strip(),'384MiB')

def devices():
 yield from select();win.tabs.set_visible_child_name('de')
 host=out/'shared';host.mkdir(exist_ok=True);(host/'marker').write_text('ORCHARD_SHARE_OK\n')
 win.sh_host.set_text(str(host));win.sh_path.set_text('/mnt/orchard-audit');win.add_share()
 yield from wait(lambda:not any(t.running for k,t in win.reads.items() if k=='tab'),'Devices refresh')
 # Independent read may run before mutation has finished: wait for toast callback.
 yield from wait(lambda:'Shared ' in win.toast.get_title(),'Folder share result')
 value=yield from cli('exec',name,'--','cat','/mnt/orchard-audit/marker');assert_eq(value.strip(),'ORCHARD_SHARE_OK')
 s=socket.socket();s.bind(('127.0.0.1',0));port=s.getsockname()[1];s.close()
 win.fw_listen.set_text(str(port));win.fw_connect.set_text('43210');win.add_forward()
 yield from wait(lambda:'Forwarding host' in win.toast.get_title(),'Proxy creation')
 # A persistent guest HTTP server lets the proxy exercise both directions.
 win.tabs.set_visible_child_name('ex');win.cmd.set_text("exec nc -lk -p 43210 -e /bin/cat");win.run_cmd()
 yield from wait(lambda:name in win.exec_proc,'Guest proxy server running')
 def fetch():
  deadline=time.monotonic()+8
  while time.monotonic()<deadline:
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=1) as conn:
     conn.settimeout(1);conn.sendall(b'ORCHARD_PROXY_OK\n')
     response=conn.recv(4096)
     if b'ORCHARD_PROXY_OK' in response:return response
   except OSError:pass
   time.sleep(.1)
  raise AssertionError('Guest TCP echo not received through proxy')
 f=pool.submit(fetch);yield from wait(f.done,'Proxy TCP echo');f.result()
 win.stop_cmd();yield from wait(lambda:name not in win.exec_proc,'Stop guest command')
 win.remove_device(name,'fwd-tcp-'+str(port));win.remove_device(name,'share-mnt-orchard-audit')
 yield from wait(lambda:name not in win.instance_writes,'Serialized device removals')


def lifecycle_snapshot():
 yield from select();win.tabs.set_visible_child_name('sn');win.snap_name.set_text('audit-s1');win.snapshot()
 yield from wait(lambda:name not in win.busy,'Snapshot creation')
 snaps=yield from query('snapshot','list',name);assert any(x['name'].split('/')[-1]=='audit-s1' for x in snaps)
 yield from cli('exec',name,'--','sh','-c',"echo version-two >/root/orchard-audit.txt")
 win.toggle_pause();yield from wait(lambda:name not in win.busy,'pause');win.refresh();yield from wait(lambda:win.data[name]['status']=='Frozen','Frozen state')
 win.toggle_pause();yield from wait(lambda:name not in win.busy,'resume');win.refresh();yield from wait(lambda:win.data[name]['status']=='Running','Running after resume')
 yield from state('restart',expected='Running');yield from state('stop',expected='Stopped')
 win.snap_op(name,'restore','audit-s1',True);yield from accept(dialog());yield from wait(lambda:'Restored audit-s1' in win.toast.get_title(),'Snapshot restore',60)
 yield from state('start',expected='Running')
 data=yield from cli('exec',name,'--','cat','/root/orchard-audit.txt');assert_eq(data.strip(),'version-one')
 yield from state('stop',expected='Stopped')

def clone_rename_delete():
 yield from select();win.clone();d=dialog('Clone '+name);e=next(x for x in walk(d) if isinstance(x,Gtk.Entry));e.set_text(clone);yield from accept(d,clone)
 yield from wait(lambda:clone in win.data,'Clone inventory',90)
 yield from select(clone);win.rename();d=dialog('Rename '+clone);e=next(x for x in walk(d) if isinstance(x,Gtk.Entry));e.set_text(renamed);yield from accept(d,renamed)
 yield from wait(lambda:renamed in win.data and clone not in win.data,'Rename inventory')
 yield from select(renamed);win.delete();yield from accept(dialog());yield from wait(lambda:renamed not in win.data,'Delete inventory')
 yield from state('start',expected='Running')

def virtual_machine():
 vm_image=next(x['fingerprint'] for x in images if x.get('type')=='virtual-machine' and 'Alpine' in x.get('properties',{}).get('description',''))
 win.on_new();d=dialog('New Instance');grid=next(x for x in walk(d) if isinstance(x,Gtk.Grid))
 grid.get_child_at(1,0).set_text(vm_name);grid.get_child_at(1,1).set_selected(len(backend.PRESETS)-1);grid.get_child_at(1,2).set_text(vm_image);grid.get_child_at(1,3).set_active(True);grid.get_child_at(1,4).set_active(False);grid.get_child_at(1,5).set_text('1');grid.get_child_at(1,6).set_text('1GiB');yield from accept(d,vm_name)
 yield from wait(lambda:vm_name not in win.jobs,'VM create completion',90)
 yield from select(vm_name)
 def agent():
  deadline=time.monotonic()+60
  while time.monotonic()<deadline:
   try:return backend.incus('exec',vm_name,'--','true',timeout=4)
   except RuntimeError:time.sleep(.5)
  raise AssertionError('VM agent not ready')
 f=pool.submit(agent);yield from wait(f.done,'VM agent',65);f.result()
 win.tabs.set_visible_child_name('ex');win.cmd.set_text('uname -m; echo ORCHARD_VM_OK');win.run_cmd()
 yield from wait(lambda:vm_name not in win.exec_proc,'VM Run command')
 assert 'ORCHARD_VM_OK' in textbuffer(win.exec_buf(vm_name))
 win.delete();yield from accept(dialog());yield from wait(lambda:vm_name not in win.data,'VM deletion',60)
 yield from select()

def native_shell_and_portals():
 yield from select()
 # A one-shot profile in the disposable guest proves Terminal reaches a login
 # shell, then exits it without injecting keyboard events into the desktop.
 profile=out/'terminal-profile.sh'
 profile.write_text("printf ORCHARD_TERMINAL_OK >/root/orchard-terminal-ok; rm -f /etc/profile.d/99-orchard-audit.sh; exit 0\n")
 yield from cli('file','push',str(profile),name+'/etc/profile.d/99-orchard-audit.sh')
 win.shell()
 def terminal_ready():
  deadline=time.monotonic()+12
  while time.monotonic()<deadline:
   try:
    if 'ORCHARD_TERMINAL_OK' in backend.incus('exec',name,'--','cat','/root/orchard-terminal-ok',timeout=3):return True
   except RuntimeError:pass
   time.sleep(.15)
  raise AssertionError('Native Terminal did not reach the guest login shell')
 f=pool.submit(terminal_ready);yield from wait(f.done,'Native Terminal login');assert f.result()
 dest=out/(name+'-backup.tar.gz')
 win.export_backup()
 helper=str(pathlib.Path(__file__).with_name('wayland-save-portal.py'))
 f=pool.submit(subprocess.run,[sys.executable,helper,'Export backup',name+'.tar.gz',str(dest)],capture_output=True,text=True,timeout=16)
 yield from wait(f.done,'Native export save portal',18)
 result=f.result()
 if result.returncode:raise RuntimeError(result.stderr or result.stdout)
 yield from wait(lambda:dest.exists() and name not in win.busy and 'Backup saved:' in win.toast.get_title(),'Native backup export',90)
 check=pool.submit(subprocess.run,['tar','-tf',str(dest)],capture_output=True,text=True,timeout=10)
 yield from wait(check.done,'Export archive validation');assert check.result().returncode==0
 report['native_export_bytes']=dest.stat().st_size


def cancelled_creation():
 win.start_create(cancel_name,image,backend.create_args(False,'1','256MiB'))
 yield from wait(lambda:cancel_name in win.jobs,'Cancellable creation card')
 win.jobs[cancel_name]['row'].cancel.emit('clicked')
 yield from wait(lambda:cancel_name not in win.jobs and cancel_name not in win.cleaning,'Cancelled creation cleanup',145)
 existing=yield from query('list');assert cancel_name not in {x['name'] for x in existing}


def frames():
 global tick_id,frame_handler
 yield from select();win.tabs.set_visible_child_name('ov');win.search.set_text(prefix);win.filter_instances()
 yield from wait(lambda:win.get_mapped(),'Wayland window mapped')
 clock=win.get_frame_clock()
 frame_handler=clock.connect('after-paint',lambda c:frame_refs.append(c.get_current_timings()))
 count=0;start=time.monotonic();action_at=0
 def animate(w,c):
  nonlocal count,action_at
  count+=1;win.status.set_text('Wayland frame pacing · '+str(count))
  now=time.monotonic()
  if now-action_at>.45:
   action_at=now;ts=GLib.get_monotonic_time();counter=c.get_frame_counter()
   if int((now-start)/2)%2:
    win.pages.set_visible_child_name('inst');win.tabs.set_visible_child_name(('ov','sn','ex','fi','de','se')[(count//30)%6])
   else:win.pages.set_visible_child_name('dash' if win.pages.get_visible_child_name()=='inst' else 'inst')
   actions.append((ts,counter))
  return True
 tick_id=win.add_tick_callback(animate)
 yield from wait(lambda:time.monotonic()-start>=8,'Continuous damage and navigation',12)
 win.remove_tick_callback(tick_id);tick_id=0
 until=time.monotonic()+.5;yield from wait(lambda:time.monotonic()>until,'Presentation feedback drain')
 clock.disconnect(frame_handler);frame_handler=0
 raw=[{'counter':t.get_frame_counter(),'start_us':t.get_frame_time(),'presentation_us':t.get_presentation_time(),'refresh_us':t.get_refresh_interval(),'complete':bool(t.get_complete())} for t in frame_refs if t]
 report['frames']=summarize_frames(raw,actions)
 report['frames'].update(cycle=cycle_index,elapsed=round(time.monotonic()-session_start,3),active_at_end=win.is_active(),mapped_at_end=win.get_mapped())
 report.setdefault('frame_runs',[]).append(report['frames'])
 (out/f'frames-cycle-{cycle_index}.json').write_text(json.dumps({'frames':raw,'actions':actions,'summary':report['frames']},indent=2))
 (out/'frames.json').write_text(json.dumps(raw,indent=2))
 (out/'report.json').write_text(json.dumps(report,indent=2))
 if report['frames']['status']!='complete':
  raise RuntimeError('Frame probe '+report['frames']['status']+': insufficient presentation/action coverage; inspect saved raw evidence and window visibility')
 win.pages.set_visible_child_name('inst');win.tabs.set_visible_child_name('de');win.set_default_size(780,480)
 until=time.monotonic()+.6;yield from wait(lambda:time.monotonic()>until,'Narrow layout settle')
 paint=Gtk.WidgetPaintable.new(win);snap=Gtk.Snapshot();paint.snapshot(snap,win.get_width(),win.get_height());node=snap.to_node()
 if node:win.get_renderer().render_texture(node,Graphene.Rect().init(0,0,win.get_width(),win.get_height())).save_to_png(str(out/'wayland-orchard.png'))
 report['narrow_size']=[win.get_width(),win.get_height()]


workflow_phases=[('create-dialog',creation),('duplicate-name-preserves-existing-guest',duplicate_name),('run-files-and-transfer',run_and_files),('settings',settings),('folder-and-port-devices',devices),('lifecycle-and-snapshot-restore',lifecycle_snapshot),('clone-rename-delete',clone_rename_delete),('native-vm-create-run-delete',virtual_machine),('native-terminal-and-backup-portal',native_shell_and_portals),('cancel-create-and-cleanup',cancelled_creation),('frame-presentation-and-layout',frames)]
session_start=time.monotonic()
cycle_index=0
report['started_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
report['pid']=os.getpid()
samples_file=(out/'resources.jsonl').open('w',buffering=1)
def resources():
 usage=resource.getrusage(resource.RUSAGE_SELF);children=resource.getrusage(resource.RUSAGE_CHILDREN)
 status=dict(x.split(':',1) for x in pathlib.Path('/proc/self/status').read_text().splitlines())
 smaps=dict(x.split(':',1) for x in pathlib.Path('/proc/self/smaps_rollup').read_text().splitlines()[1:] if ':' in x)
 return {'elapsed':round(time.monotonic()-session_start,3),'cycle':cycle_index,'phase':phase_name,'cpu_seconds':usage.ru_utime+usage.ru_stime,'child_cpu_seconds':children.ru_utime+children.ru_stime,
         'rss_kib':int(status['VmRSS'].split()[0]),'pss_kib':int(smaps['Pss'].split()[0]),'private_kib':sum(int(smaps.get(k,'0').split()[0]) for k in ('Private_Clean','Private_Dirty')),
         'threads':int(status['Threads']),'fds':len(list(pathlib.Path('/proc/self/fd').iterdir())),
         'active':bool(win.is_active()),'mapped':bool(win.get_mapped()),'minimized':bool(win.get_surface() and win.get_surface().get_state() & Gdk.ToplevelState.MINIMIZED),
         'buffers':len(win.exec_bufs),'buffer_chars':sum(x.get_char_count() for x in win.exec_bufs.values()),'undoable_buffers':sum(x.get_can_undo() for x in win.exec_bufs.values()),
         'histories':len(win.hist),'dashboard_rows':len(win.dash_rows),'rows':len(win.rows),'reads':len(win.reads),'sources':len(win.sources),'jobs':len(win.jobs),'commands':len(win.exec_proc),'writes':len(win.instance_writes),
         'toplevels':len(list(Gtk.Window.get_toplevels()))}
def sample_resources():
 samples_file.write(json.dumps(resources())+'\n');return True
sample_id=GLib.timeout_add_seconds(5,sample_resources)
def checkpoint():
 gc.collect()
 result=resources();result['python_tracked_objects']=len(gc.get_objects())
 return result
def idle_until(deadline):
 def run():
  win.pages.set_visible_child_name('dash')
  yield from wait(lambda:time.monotonic()>=deadline,'Idle resource observation',max(0,deadline-time.monotonic())+5)
 return run
def idle(seconds):
 def run():
  yield from idle_until(time.monotonic()+seconds)()
 return run
def cleanup_cycle():
 yield from select();win.delete();yield from accept(dialog())
 yield from wait(lambda:name not in win.data,'Cycle guest deleted',60)
 until=time.monotonic()+2
 yield from wait(lambda:time.monotonic()>until and not win.cleaning and not win.exec_proc and not win.instance_writes,'Cycle quiescent')
def prepare_cycle(cycle):
 def run():
  global name,clone,renamed,vm_name,cancel_name,frame_refs,actions,cycle_index
  cycle_index=cycle
  name=prefix+f'-c{cycle}-dev';clone=prefix+f'-c{cycle}-copy';renamed=prefix+f'-c{cycle}-renamed';vm_name=prefix+f'-c{cycle}-vm';cancel_name=prefix+f'-c{cycle}-cancel'
  owned.update((name,clone,renamed,vm_name,cancel_name));(out/'owned.json').write_text(json.dumps(sorted(owned)))
  frame_refs=[];actions=[]
  yield from wait(lambda:win.ok and not win._checking,'Cycle ready')
 return run
def session_phases():
 if a.idle_before:yield ('idle-before',idle(a.idle_before))
 for cycle in range(1,a.cycles+1):
  if a.cycle_interval and cycle>1:
   yield (f'idle-before-cycle-{cycle}',idle_until(session_start+a.idle_before+(cycle-1)*a.cycle_interval))
  yield (f'cycle-{cycle}-prepare',prepare_cycle(cycle))
  yield from workflow_phases
  yield (f'cycle-{cycle}-cleanup',cleanup_cycle)
 if a.idle_after:yield ('idle-after',idle(a.idle_after))
 if a.session_seconds:yield ('idle-session-tail',idle_until(session_start+a.session_seconds))
phases=iter(session_phases())
report['session']={'cycles':a.cycles,'idle_before_seconds':a.idle_before,'idle_after_seconds':a.idle_after,'cycle_interval_seconds':a.cycle_interval,'minimum_duration_seconds':a.session_seconds,'resource_sampling_seconds':5,'cpu_percent_definition':'100% = one CPU core; process and reaped CLI-child CPU reported separately; background daemon/VM/compositor costs excluded'}

def next_phase():
 global phase_iter,phase_name,pending,phase_start
 try:phase_name,fn=next(phases)
 except StopIteration:finish();return False
 phase_iter=fn();phase_start=time.monotonic();pending=None;print('START',phase_name,flush=True);(out/'report.json').write_text(json.dumps(report,indent=2));return True

def advance():
 global pending
 if win.closing:
  results.append({'workflow':phase_name,'cycle':cycle_index,'elapsed':round(time.monotonic()-session_start,3),'passed':False,'error':'Audit window was closed; session interrupted'})
  finish();return False
 try:
  if pending:
   pred,label,deadline,errcount=pending
   if len(errors)>errcount:raise RuntimeError(errors[-1])
   if not pred():
    if time.monotonic()>deadline:raise TimeoutError(label)
    return True
   pending=None
  pred,label,seconds=next(phase_iter);print('WAIT',label,flush=True);pending=(pred,label,time.monotonic()+seconds,len(errors))
 except StopIteration:
  results.append({'workflow':phase_name,'cycle':cycle_index,'elapsed':round(time.monotonic()-session_start,3),'passed':True,'seconds':round(time.monotonic()-phase_start,2),'resources':checkpoint()});print('PASS',phase_name,flush=True)
  return next_phase()
 except Exception as e:
  results.append({'workflow':phase_name,'cycle':cycle_index,'elapsed':round(time.monotonic()-session_start,3),'passed':False,'error':str(e)});traceback.print_exc()
  if phase_name=='create-dialog':finish();return False
  return next_phase()
 return True

def cleanup_owned_guests():
 # Closing during a metadata write can briefly leave Incus's update lock held.
 # Recheck both exact name and creation token on every bounded retry.
 existing={x['name'] for x in backend.ijson('list')}
 for n in sorted(owned & existing):
  for attempt in range(10):
   current=next((x for x in backend.ijson('list') if x['name']==n),None)
   if current is None or (current.get('config') or {}).get(backend.CREATION_TOKEN_KEY) not in created_tokens:
    break
   try:
    backend.incus('delete','--force',n,timeout=60)
    break
   except RuntimeError as error:
    if 'busy running' not in str(error).lower() or attempt==9:raise
    time.sleep(.5)

def finish():
 global tick_id,frame_handler
 if tick_id:win.remove_tick_callback(tick_id)
 clock=win.get_frame_clock()
 if frame_handler and clock:clock.disconnect(frame_handler)
 sample_resources();GLib.source_remove(sample_id);samples_file.close()
 win.close()
 def clean():
  cleanup_owned_guests()
  final={x['name']:x['status'] for x in backend.ijson('list')}
  report['cleanup']={'owned_remaining':sorted(owned & final.keys()),'existing_guests_preserved':all(final.get(n)==s for n,s in initial.items())}
  report['session']['elapsed_seconds']=round(time.monotonic()-session_start,3)
  report['qualification']={'passed':not errors and all(x['passed'] for x in results) and report['cleanup']['existing_guests_preserved'] and not report['cleanup']['owned_remaining'] and report['session']['elapsed_seconds']>=a.session_seconds and sum(x['workflow'].endswith('-cleanup') and x['passed'] for x in results)==a.cycles,'completed_cycles':sum(x['workflow'].endswith('-cleanup') and x['passed'] for x in results),'required_cycles':a.cycles,'duration_met':report['session']['elapsed_seconds']>=a.session_seconds}
  report['ended_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
  report['expected_errors']=expected_errors;report['errors']=errors;(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
 def cleanup_ended(future):
  try:
   error=future.exception()
   if error:
    report['cleanup']={'error':str(error)}
    report['session']['elapsed_seconds']=round(time.monotonic()-session_start,3)
    report['ended_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
    report['qualification']={'passed':False,'reason':'Cleanup failed'}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
  finally:
   GLib.idle_add(loop.quit)
 pool.submit(clean).add_done_callback(cleanup_ended)
try:
 def step():
  if advance():GLib.timeout_add(1000 if phase_name.startswith('idle-') else 25,step)
  return False
 next_phase();GLib.timeout_add(25,step);loop.run()
finally:
 win.close()
 if 'cleanup' not in report:
  cleanup_owned_guests()
 pool.shutdown(wait=True)
print(json.dumps(report,indent=2),flush=True)
if not report.get('qualification',{}).get('passed') or errors or any(not r['passed'] for r in results) or report.get('cleanup',{}).get('error') or report.get('cleanup',{}).get('owned_remaining') or not report.get('cleanup',{}).get('existing_guests_preserved'):
 sys.exit(1)
