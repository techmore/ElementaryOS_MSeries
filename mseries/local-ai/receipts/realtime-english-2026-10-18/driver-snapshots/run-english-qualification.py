import fcntl,hashlib,json,os,platform,signal,subprocess,sys,time
from pathlib import Path
work=Path(__file__).resolve().parent;repo=work/'ElementaryOS_MSeries';root=work/'english-realtime-v1';root.mkdir(exist_ok=True,mode=0o700)
lock=(work/'realtime-speech-v1/queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
source=root/'evaluated-source/dictation';source.mkdir(exist_ok=True,parents=True);(source.parent/'local-ai').mkdir(exist_ok=True)
for p in (repo/'mseries/dictation').glob('*.py'):
 dest=source/p.name
 if dest.exists():assert dest.read_bytes()==p.read_bytes()
 else:dest.write_bytes(p.read_bytes())
(source.parent/'local-ai/machine.py').write_bytes((repo/'mseries/local-ai/machine.py').read_bytes())
sys.path.insert(0,str(source));from dictation_resources import snapshot,load_policy,reasons
policy=load_policy();identity={'kernel':platform.release(),'policy':policy,'source_sha256':{p.relative_to(source.parent).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.parent.rglob('*.py')}}
status=root/'queue.json'
def save(row):
 row['identity']=identity;p=status.with_suffix('.tmp');p.write_text(json.dumps(row,indent=2)+'\n');p.replace(status)
def busy():
 if subprocess.run(['pgrep','-x','rustc|oha'],capture_output=True).returncode==0:return True
 from dictation_status import read_status
 row=read_status()
 if row and row['phase'] in ('loading','listening','finishing'):
  try:os.kill(row['pid'],0);return True
  except ProcessLookupError:pass
 return False
def descendants(pid):
 try:children=[int(x) for x in Path(f'/proc/{pid}/task/{pid}/children').read_text().split()]
 except OSError:return []
 return [x for child in children for x in [*descendants(child),child]]
def stop_owned(child):
 for pid in [*descendants(child.pid),child.pid]:
  try:os.kill(pid,signal.SIGTERM)
  except ProcessLookupError:pass
 try:child.wait(4)
 except subprocess.TimeoutExpired:child.kill();child.wait()
python=Path.home()/'.local/share/mseries/stream/venv/bin/python';assets=work/'speech-assets'
steps=[('ane-rolling',[str(python),str(source/'ane-realtime-bench.py'),'--wav',str(Path.home()/'.local/share/mseries/stream/libri.wav'),'--output',str(root/'ane-rolling.json')])]
clips=json.loads((assets/'public-clips/expanded-manifest.json').read_text())
for engine,model in [('nemotron-160-cpu',assets/'nemotron-speech-streaming-en-0.6b-Q8_0.gguf'),('unified-cpu',Path.home()/'.local/share/mseries/stream/models/parakeet-unified-en-0.6b-Q4_K_M.gguf')]:
 for clip in clips:
  label=engine+'-'+clip['id'];steps.append((label,[str(python),str(source/'realtime-bench.py'),'--engine',engine,'--model',str(model),'--wav',str(assets/'public-clips'/(clip['id']+'-16k.wav')),'--reference-file',str(assets/'public-clips'/(clip['id']+'.txt')),'--runs','1','--output',str(root/(label+'.json'))]))
steps.append(('english-panel',['/usr/bin/python3',str(source/'english-workflow-smoke.py'),'--receipt-dir',str(root/'english-panel'),'--asr-engine','nemotron-160-cpu','--cpu-assets',str(assets),'--previews']))
for name,command in steps:
 attempt=root/(name+'-attempt.json')
 if attempt.exists() or (root/name).exists() or (root/(name+'.json')).exists():print('Preserving evidence '+name,flush=True);continue
 stable=0
 while stable<3:
  assert platform.release()==identity['kernel'] and load_policy()==policy
  s=snapshot();good=not reasons(policy,2*1024**3,s) and max(s['fans_rpm'].values(),default=9999)<2700 and max(s['temperatures_c'].values(),default=999)<60 and not busy()
  stable=stable+1 if good else 0;save({'state':'waiting','step':name,'stable_samples':stable})
  if stable<3:time.sleep(10)
 env=dict(os.environ,OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',TRANSCRIBE_LIBRARY=str(Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'))
 log=(root/(name+'-private.log')).open('w');start=time.monotonic();samples=[];interruption=None;family_rss=[]
 child=subprocess.Popen(command,stdout=log,stderr=log,env=env,start_new_session=True);save({'state':'running','step':name,'pid':child.pid})
 while child.poll() is None:
  s=snapshot();samples.append(s)
  rss=0
  for pid in [child.pid,*descendants(child.pid)]:
   try:
    for line in Path(f'/proc/{pid}/status').read_text().splitlines():
     if line.startswith('VmRSS:'):rss+=int(line.split()[1])*1024
   except OSError:pass
  family_rss.append(rss)
  if reasons(policy,0,s) or max(s['fans_rpm'].values(),default=9999)>=2700 or max(s['temperatures_c'].values(),default=999)>=63:interruption='quiet-or-reserve-guard'
  if busy():interruption='owner-load-or-capture-started'
  if time.monotonic()-start>240:interruption='owned-worker-timeout'
  if interruption:stop_owned(child);break
  time.sleep(.5)
 rc=child.wait();log.close();attempt.write_text(json.dumps({'step':name,'exit_code':rc,'interruption':interruption,'wall_s':time.monotonic()-start,'identity':identity,'resources':{'samples':len(samples),'min_available_bytes':min(s['available_bytes'] for s in samples),'max_fan_rpm':max(max(s['fans_rpm'].values(),default=9999) for s in samples),'max_temp_c':max(max(s['temperatures_c'].values(),default=999) for s in samples),'peak_process_family_rss_sum_bytes':max(family_rss),'rss_scope':'RSS summed over owned descendants; shared pages may be counted more than once, not physical memory/PSS.'}},indent=2)+'\n')
 print(json.dumps({'step':name,'exit_code':rc,'interruption':interruption}),flush=True)
 if interruption:break
save({'state':'terminal','scope':'Retain all outcomes; no automatic comparable reruns'})
