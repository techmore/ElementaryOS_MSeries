"""Eight guarded native CPU load/close cycles; no inference/audio/desktop access."""
import hashlib,importlib.util,json,os,sys,time
from pathlib import Path
base=Path(__file__).resolve().parent
repo=base/'ElementaryOS_MSeries'
out=base/'dictation-reload-soak-v1';out.mkdir(mode=0o700)
source=out/'evaluated-source';source.mkdir()
for name in ['stream-dictate.py','dictation_model.py','dictation_status.py','dictation_resources.py']:
 (source/name).write_bytes((repo/'mseries/dictation'/name).read_bytes())
(source/'machine.py').write_bytes((repo/'mseries/local-ai/machine.py').read_bytes())
(source/'run-dictation-reload-soak.py').write_bytes(Path(__file__).read_bytes())
sys.path.insert(0,str(source))
from dictation_resources import load_policy,reasons,snapshot
spec=importlib.util.spec_from_file_location('reload_soak_stream',source/'stream-dictate.py');stream=importlib.util.module_from_spec(spec);spec.loader.exec_module(stream)
assert os.environ.get('STREAM_DRY')=='1' and os.environ.get('STREAM_BACKEND')=='cpu'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for block in iter(lambda:f.read(1024**2),b''):h.update(block)
 return h.hexdigest()
def rss():return int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmRSS:')))*1024
profile=Path.home()/'.config/mseries-ai/profiles.json'
r={'complete':False,'passed':False,'cycles':[],'kernel':os.uname().release,'policy':load_policy(),'profile_sha256':sha(profile),'source_sha256':{p.name:sha(p) for p in source.glob('*.py')},'model_sha256':sha(Path(stream.MODEL)),'native_library_sha256':sha(Path(os.environ['TRANSCRIBE_LIBRARY'])),'inference_runs':0,'microphone_recorded':False,'keyboard_device_opened':False,'owner_windows_opened':False}
def save():
 tmp=out/'receipt.tmp';tmp.write_text(json.dumps(r,indent=2)+'\n');tmp.chmod(0o600);os.replace(tmp,out/'receipt.json')
save();d=stream.Dictation();samples=[]
try:
 for index in range(8):
  stable=0
  while stable<3:
   sample=snapshot();samples.append(sample)
   assert sha(profile)==r['profile_sha256'] and os.uname().release==r['kernel']
   ready=not reasons(r['policy'],1024**3,sample) and max(sample['fans_rpm'].values(),default=9999)<2700 and max(sample['temperatures_c'].values(),default=999)<=63
   stable=stable+1 if ready else 0;time.sleep(2)
  with d.models.use(lambda extra:not reasons(r['policy'],extra)) as model:
   assert model._handle is not None
   loaded=rss()
  assert d.models.trim(force=True) and model._handle is None
  sample=snapshot();samples.append(sample)
  if reasons(r['policy'],sample=sample):r['interrupted']=True;raise RuntimeError('Owned reload soak guard; no model quality score')
  r['cycles'].append({'cycle':index+1,'resident_rss_bytes':loaded,'released_rss_bytes':rss()});save()
 tail=[x['released_rss_bytes'] for x in r['cycles'][-4:]]
 r.update(complete=True,passed=True,tail_closed_rss_range_bytes=max(tail)-min(tail),scope='Eight no-inference native CPU reloads; short bounded memory observations, not an always-on lifetime or leak-free claim.')
except Exception as e:r['failure_kind']=type(e).__name__;raise
finally:
 d.models.trim(force=True)
 r['resources']={'samples':len(samples),'min_available_bytes':min(x['available_bytes'] for x in samples),'max_fan_rpm':max(max(x['fans_rpm'].values()) for x in samples),'max_temp_c':max(max(x['temperatures_c'].values()) for x in samples)}
 save()
print(json.dumps({'complete':r['complete'],'closed_mib':[round(x['released_rss_bytes']/1024**2,2) for x in r['cycles']]}))
