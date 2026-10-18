import fcntl,hashlib,json,os,platform,signal,subprocess,sys,time
from pathlib import Path
work=Path(__file__).resolve().parent;repo=work/'ElementaryOS_MSeries';sys.path.insert(0,str(repo/'mseries/dictation'))
from dictation_resources import load_policy,snapshot,reasons
root=work/'realtime-nemotron-v2';root.mkdir(exist_ok=True,mode=0o700)
lock=(work/'realtime-speech-v1/queue.lock').open('a')
while True:
 try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);break
 except BlockingIOError:time.sleep(5)
source=root/'realtime-bench.py';current=repo/'mseries/dictation/realtime-bench.py'
if source.exists():assert source.read_bytes()==current.read_bytes()
else:source.write_bytes(current.read_bytes())
policy=load_policy();identity={'kernel':platform.release(),'policy':policy,'harness_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
status=root/'queue.json'
def save(row):
 row['identity']=identity;tmp=status.with_suffix('.tmp');tmp.write_text(json.dumps(row,indent=2)+'\n');tmp.replace(status)
def busy():return subprocess.run(['pgrep','-x','rustc|oha'],capture_output=True).returncode==0
assets=work/'speech-assets/download.moonshine.ai/model'
engines=[(name,Path.home()/'.local/share/mseries/stream/venv/bin/python',work/'speech-assets/nemotron-speech-streaming-en-0.6b-Q8_0.gguf') for name in ['nemotron-160-cpu','nemotron-560-cpu']]
for engine,python,model in engines:
 dest=root/(engine+'.json');attempt=root/(engine+'-attempt.json')
 if dest.exists() or attempt.exists():
  print('Preserving existing evidence for '+engine,flush=True);continue
 stable=0
 while stable<3:
  assert platform.release()==identity['kernel'] and load_policy()==policy
  s=snapshot();why=reasons(policy,1024**3,s)
  good=not why and max(s['fans_rpm'].values(),default=9999)<2700 and max(s['temperatures_c'].values(),default=999)<60 and not busy()
  stable=stable+1 if good else 0
  save({'state':'waiting','engine':engine,'stable_samples':stable,'available_bytes':s['available_bytes'],'max_fan_rpm':max(s['fans_rpm'].values(),default=None),'max_temp_c':max(s['temperatures_c'].values(),default=None)})
  if stable<3:time.sleep(10)
 manifest={p.relative_to(model).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in model.rglob('*') if p.is_file()} if model.is_dir() else {'weights':hashlib.sha256(model.read_bytes()).hexdigest()}
 env=dict(os.environ,OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1',TRANSCRIBE_LIBRARY=str(Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'))
 log=(root/(engine+'-private.log')).open('w');started=time.monotonic();samples=[];interrupt=None
 child=subprocess.Popen([str(python),str(source),'--engine',engine,'--model',str(model),'--wav',str(Path.home()/'.local/share/mseries/stream/libri.wav'),'--output',str(dest)],stdout=log,stderr=log,env=env,start_new_session=True)
 save({'state':'running','engine':engine,'child_pid':child.pid})
 while child.poll() is None:
  s=snapshot();samples.append(s)
  if reasons(policy,0,s) or max(s['fans_rpm'].values(),default=9999)>=2700 or max(s['temperatures_c'].values(),default=999)>=63:interrupt='quiet-or-reserve-guard'
  if busy():interrupt='owner-load-test-started'
  if time.monotonic()-started>100:interrupt='owned-worker-timeout'
  if interrupt:
   os.killpg(child.pid,signal.SIGTERM)
   try:child.wait(3)
   except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
   break
  time.sleep(.5)
 rc=child.wait();log.close()
 row={'engine':engine,'exit_code':rc,'interruption':interrupt,'wall_s':time.monotonic()-started,'model_sha256':manifest,'identity':identity,'resources':{'samples':len(samples),'min_available_bytes':min(x['available_bytes'] for x in samples),'max_fan_rpm':max(max(x['fans_rpm'].values(),default=9999) for x in samples),'max_temp_c':max(max(x['temperatures_c'].values(),default=999) for x in samples)},'quality_score':None if interrupt or rc else 'See each retained WER, not a pass/fail quality aggregate'}
 attempt.write_text(json.dumps(row,indent=2)+'\n');print(json.dumps({'engine':engine,'exit_code':rc,'interruption':interrupt}),flush=True)
 if interrupt:break
save({'state':'terminal','scope':'Inspect retained worker/attempt receipts; failures and interruptions not repeated automatically'})
