import fcntl,hashlib,json,os,signal,subprocess,sys,time
from pathlib import Path
w=Path(__file__).resolve().parent;r=w/'ElementaryOS_MSeries';root=w/'f5-installed-v1';root.mkdir(exist_ok=True,mode=0o700)
lock=(w/'realtime-speech-v1/queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX)
sys.path.insert(0,str(r/'mseries/dictation'));from dictation_resources import snapshot,load_policy,reasons
from dictation_status import read_status
policy=load_policy();policy.update(max_fan_rpm=2700,max_temp_c=63,reserve_gib=max(6,policy['reserve_gib']))
base=Path.home()/'.local/share/mseries/stream'
def descendants(pid):
 try:cs=[int(x) for x in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
 except OSError:return []
 return [x for ch in cs for x in [*descendants(ch),ch]]
def busy():
 if subprocess.run(['pgrep','-x','rustc|oha'],capture_output=True).returncode==0:return True
 row=read_status()
 if row and row['phase'] in ['loading','listening','finishing']:
  try:os.kill(row['pid'],0);return True
  except ProcessLookupError:pass
 return False
steps=[]
for framework in ['gtk4','gtk3','qt6','brave']:
 command=['/usr/bin/python3',str(r/'mseries/dictation/f5-app-qualification.py'),'--framework',framework,'--payload-dir',str(base),'--model',str(base/'models/nemotron-speech-streaming-en-0.6b-Q8_0.gguf'),'--receipt-dir',str(root/framework)]
 if framework!='gtk4':command+=['--fixtures-only']
 steps.append((framework,command))
for app in ['code','newelle','tasks']:
 command=['/usr/bin/python3',str(r/'mseries/dictation/f5-real-apps-qualification.py'),'--app',app,'--payload-dir',str(base),'--fixtures-only','--receipt-dir',str(root/app)]
 if app=='tasks':command+=['--software-wm']
 steps.append((app,command))
for name,command in steps:
 attempt=root/(name+'-attempt.json')
 if attempt.exists()or(root/name).exists():print('Retaining '+name,flush=True);continue
 stable=0
 while stable<3:
  s=snapshot();ok=not reasons(policy,2*1024**3,s) and max(s['temperatures_c'].values(),default=999)<60 and not busy();stable=stable+1 if ok else 0
  if stable<3:time.sleep(3)
 log=(root/(name+'-private.log')).open('w');start=time.monotonic();samples=[];reason=None;p=subprocess.Popen(command,stdout=log,stderr=log,start_new_session=True)
 while p.poll() is None:
  s=snapshot();samples.append(s)
  if reasons(policy,0,s) or busy():reason='quiet-reserve-or-owner-load'
  if time.monotonic()-start>180:reason='deadline'
  if reason:
   for pid in [*descendants(p.pid),p.pid]:
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:pass
   try:p.wait(4)
   except subprocess.TimeoutExpired:p.kill();p.wait()
   break
  time.sleep(.5)
 rc=p.wait();log.close();attempt.write_text(json.dumps({'complete':True,'exit_code':rc,'interruption':reason,'policy':policy,'resources':{'min_available_bytes':min(x['available_bytes'] for x in samples),'max_fan_rpm':max(max(x['fans_rpm'].values(),default=9999) for x in samples),'max_temp_c':max(max(x['temperatures_c'].values(),default=999) for x in samples)}},indent=2)+'\n');print(json.dumps({'case':name,'exit_code':rc,'interruption':reason}),flush=True)
 if reason:break
