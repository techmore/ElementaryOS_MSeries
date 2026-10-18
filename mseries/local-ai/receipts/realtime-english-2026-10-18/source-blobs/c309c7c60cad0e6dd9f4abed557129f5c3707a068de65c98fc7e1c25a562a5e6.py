#!/usr/bin/python3
"""Wall-paced file-only rolling ANE controller probe. No keyboard, mic or app insertion."""
import argparse,hashlib,importlib.util,json,os,resource,sys,time,types
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wav',type=Path,required=True);a=p.parse_args()
if a.output.exists():raise SystemExit('Retain completed/interrupted evidence')
HERE=Path(__file__).resolve().parent
os.environ.update(STREAM_ENGINE='ane',STREAM_DRY='1',STREAM_QUIET='1',STREAM_TEST_WAV=str(a.wav.resolve()),STREAM_OUTPUT='ibus')
for key in ['STREAM_KEEP','STREAM_TEST_RAW','STREAM_TEST_INSERT']:os.environ.pop(key,None)
spec=importlib.util.spec_from_file_location('ane_paced_controller',HERE/'stream-dictate.py');controller=importlib.util.module_from_spec(spec);spec.loader.exec_module(controller)
report={'complete':False,'engine':'ane-rolling','microphone_recorded':False,'keyboard_device_opened':False,'owner_windows_opened':False,
    'wav_sha256':hashlib.sha256(a.wav.read_bytes()).hexdigest(),'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    'controller_sha256':hashlib.sha256((HERE/'stream-dictate.py').read_bytes()).hexdigest(),'trials':[],
    'scope':'Actual rolling ANE controller and existing native runtime, file-paced ffmpeg. Synthetic immediate text sink; no desktop insertion. First run cold, later runs reuse the same worker. Controller RSS excludes native child workers; inspect supervised process-family resources separately.'}
started=0;events=[]
class Sink:
    def __init__(self,*_):self.q=types.SimpleNamespace(unfinished_tasks=0);self.failed=False
    def submit(self,text,token):events.append({'wall_s':time.monotonic()-started,'text':text})
    def finish(self,token):pass
    def drain(self,*_):return True
controller.Typer=Sink;d=controller.Dictation()
def checkpoint():
    t=a.output.with_suffix('.tmp');t.write_text(json.dumps(report,indent=2)+'\n');t.replace(a.output)
checkpoint()
try:
    for run in range(3):
        events=[];started=time.monotonic();d.start();d.worker.join(90)
        if d.worker.is_alive():raise TimeoutError('Owned ANE controller timed out')
        if d.error:raise RuntimeError(d.error)
        report['trials'].append({'run':run+1,'events':events,'elapsed_s':time.monotonic()-started,
            'first_text_s':next((e['wall_s'] for e in events if e['text'].strip()),None),'final_text':''.join(e['text'] for e in events).strip(),
            'controller_peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024})
        checkpoint()
finally:d.models.trim(force=True)
report['complete']=True;checkpoint()
