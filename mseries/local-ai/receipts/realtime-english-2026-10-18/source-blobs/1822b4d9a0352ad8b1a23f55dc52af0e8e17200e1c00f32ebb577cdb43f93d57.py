#!/usr/bin/python3
"""File-only MLX Vulkan Parakeet rolling-preview experiment; no microphone or typing.

Uses Omarchy's documented pinned mlx-audio0.5.6 model. The bare-family import
follows Joshua Warren/mlx-omarchy's MIT gpu_stt_worker.py to avoid unrelated
model-family initialization. This adapter's rolling-prefix policy is experimental.
"""
import argparse,hashlib,importlib.util,json,sys,time,wave
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
for name in ['model','modules','wav','output']:p.add_argument('--'+name,type=Path,required=True)
a=p.parse_args()
if a.output.exists():raise SystemExit('Retain existing evidence')
r={'complete':False,'engine':'mlx-vulkan-parakeet-rolling','microphone_recorded':False,'owner_windows_opened':False,
   'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'trials':[],
   'scope':'Wall-paced rolling prefixes through resident pinned mlx-audio Parakeet on Omarchy-MLX Vulkan. No microphone/desktop insertion. Draft text is revisable; stable prefixes use two agreeing passes. Native hardware dispatch not independently instrumented.'}
def checkpoint():
 t=a.output.with_suffix('.tmp');t.write_text(json.dumps(r,indent=2)+'\n');t.replace(a.output)
checkpoint()
try:
 sys.path.insert(0,str(a.modules));import importlib.metadata
 assert importlib.metadata.version('mlx-audio')=='0.5.6'
 import numpy as np,mlx.core as mx
 from dictation_ane import stable_count
 from importlib.util import spec_from_file_location,module_from_spec
 spec=spec_from_file_location('realtime_metrics',Path(__file__).with_name('realtime-bench.py'));metrics=module_from_spec(spec);spec.loader.exec_module(metrics)
 # Import the family lazily, as upstream's qualified GPU speech worker does.
 name='mlx_audio.stt.models';spec=importlib.util.find_spec(name);sys.modules[name]=importlib.util.module_from_spec(spec)
 from mlx_audio.stt.utils import load_model
 r['mlx_version']=mx.__version__;r['mlx_audio_version']='0.5.6'
 with wave.open(str(a.wav)) as w:
  assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(16000,1,2)
  pcm=np.frombuffer(w.readframes(w.getnframes()),'<i2').astype(np.float32)/32768
 start=time.monotonic();model=load_model(a.model);r['load_s']=time.monotonic()-start;checkpoint()
 start=time.monotonic();model.generate(mx.zeros((16000,),dtype=mx.float32),verbose=False);r['silence_warm_s']=time.monotonic()-start;checkpoint()
 for run in range(3):
  events=[];previous=[];committed=[];start=time.monotonic();offset=16000
  while True:
   offset=min(offset,len(pcm));due=start+offset/16000;time.sleep(max(0,due-time.monotonic()))
   with mx.stream(mx.gpu):
    result=model.generate(mx.array(pcm[:offset]),verbose=False)
   text=str(getattr(result,'text','') or '');words=text.split();n=stable_count(previous,words)
   if n>len(committed):committed=words[:n]
   events.append({'wall_s':time.monotonic()-start,'audio_s':offset/16000,'draft':text,'stable':' '.join(committed)})
   previous=words
   if offset==len(pcm):break
   # Consume newly available audio after compute; never pretend processing time is free.
   offset=max(offset+4800,int((time.monotonic()-start)*16000))
  r['trials'].append({'run':run+1,'first_text_s':next((e['wall_s'] for e in events if e['draft']),None),
   'first_stable_s':next((e['wall_s'] for e in events if e['stable']),None),'final_after_audio_s':time.monotonic()-start-len(pcm)/16000,
   'final_text':text,'normalized_wer':metrics.wer(metrics.REFERENCE,text),'events':events,'mlx_peak_memory_bytes':int(mx.get_peak_memory())})
  checkpoint()
 r['complete']=True;checkpoint()
except Exception as error:
 r['failure_kind']=type(error).__name__;r['failure_detail']=str(error)[:1200];r['quality_score']=None;checkpoint();raise
