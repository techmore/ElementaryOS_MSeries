#!/usr/bin/python3
"""Public WAV → actual private GTK4 English words/optional English suggestions. No microphone."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--receipt-dir',type=Path,required=True)
p.add_argument('--wav',type=Path,default=Path.home()/'.local/share/mseries/stream/libri.wav')
p.add_argument('--asr-engine',choices=['unified-cpu','nemotron-160-cpu'],default='nemotron-160-cpu')
p.add_argument('--previews',action='store_true')
p.add_argument('--cpu-assets',type=Path)
p.add_argument('--asr-worker',action='store_true')
a=p.parse_args();HERE=Path(__file__).resolve().parent
if a.asr_worker:
    import wave,numpy as np,transcribe_cpp as tc
    with wave.open(str(a.wav)) as w:
        assert (w.getframerate(),w.getnchannels(),w.getsampwidth())==(16000,1,2)
        audio=np.frombuffer(w.readframes(w.getnframes()),'<i2').astype(np.float32)/32768
    weights=(a.cpu_assets/'nemotron-speech-streaming-en-0.6b-Q8_0.gguf' if a.asr_engine=='nemotron-160-cpu' else Path.home()/'.local/share/mseries/stream/models/parakeet-unified-en-0.6b-Q4_K_M.gguf')
    options = {'family':tc.ParakeetStreamOptions(att_context_right=1)} if a.asr_engine=='nemotron-160-cpu' else {}
    with tc.Model(str(weights),backend='cpu') as model,model.session(n_threads=4) as session,session.stream(**options) as stream:
        start=time.monotonic();previous=''
        for offset in range(0,len(audio),1600):
            chunk=audio[offset:offset+1600];due=start+(offset+len(chunk))/16000
            time.sleep(max(0,due-time.monotonic()));stream.feed(chunk);text=stream.text().display.strip()
            if text!=previous:
                print(json.dumps({'text':text,'final':False,'wall_s':time.monotonic()-start}),flush=True);previous=text
        stream.finalize()
        print(json.dumps({'text':stream.text().display.strip(),'final':True,'wall_s':time.monotonic()-start}),flush=True)
    raise SystemExit(0)
if os.environ.get('MSERIES_LIVE_WORKFLOW')!='1':
    owner=os.environ.get('DBUS_SESSION_BUS_ADDRESS','unix:path=/run/user/'+str(os.getuid())+'/bus')
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env','MSERIES_LIVE_WORKFLOW=1',
        'MSERIES_REVIEW_OWNER_BUS='+owner,'GSETTINGS_BACKEND=memory','GSK_RENDERER=cairo','GDK_BACKEND=x11',
        sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]]).returncode)
assert os.environ['GSETTINGS_BACKEND']=='memory'
root=a.receipt_dir.resolve();root.mkdir(exist_ok=False,parents=True,mode=0o700)
source=root/'evaluated-source/dictation';source.mkdir(parents=True);(source.parent/'local-ai').mkdir()
for name in ['dictation-panel.py','dictation_live.py','dictation_review.py','dictation_pipeline.py','dictation_status.py','dictation_resources.py','dictation_model.py','review-smoke.py','english-workflow-smoke.py']:
    (source/name).write_bytes((HERE/name).read_bytes())
(source.parent/'local-ai/machine.py').write_bytes((HERE.parent/'local-ai/machine.py').read_bytes())
sys.path.insert(0,str(source))
from dictation_resources import snapshot,load_policy,reasons
from dictation_review import ReviewUnavailable
spec=importlib.util.spec_from_file_location('live_bench_admission',source/'review-smoke.py');bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
identity=bench.metadata();bench.wait_ready(False,identity)
import gi
gi.require_version('Gtk','4.0')
from gi.repository import GLib
spec=importlib.util.spec_from_file_location('live_native_panel',source/'dictation-panel.py');panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
report={'complete':False,'passed':False,'language':'English','asr_engine':a.asr_engine,'runtime':identity,'source_sha256':{p.relative_to(source.parent).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.parent.rglob('*.py')},
    'microphone_recorded':False,'owner_windows_opened':False,'wav_sha256':hashlib.sha256(a.wav.read_bytes()).hexdigest(),
    'source_events':[],'proposal_events':[],'model_stages':[],'method':'Real CPU ASR from wall-paced public WAV, actual private GTK4 widgets; one existing supervised4B endpoint; English grammar review only. No physical keyboard, ambient recording or global input.'}
started=time.monotonic();samples=[];phase=['listening'];asr=cpu=None;app=None;next_sample=0
stop=threading.Event();
def checkpoint():
    tmp=root/'receipt.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(root/'receipt.json')
def pump(seconds=.05):
    global next_sample
    until=time.monotonic()+seconds
    while time.monotonic()<until:
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        if time.monotonic()>=next_sample:
            s=snapshot();samples.append(s);next_sample=time.monotonic()+.5
            if reasons(identity['policy'],0,s) or max(s['fans_rpm'].values(),default=9999)>=2700 or max(s['temperatures_c'].values(),default=999)>=63:
                report['interruption']='quiet-or-reserve-guard';raise RuntimeError('Quiet policy interrupted owned workflow')
        time.sleep(.01)
def until(condition,timeout=100):
    deadline=time.monotonic()+timeout
    while not condition():
        if time.monotonic()>deadline:raise TimeoutError('Owned workflow timed out')
        pump()
checkpoint()
try:
    app=panel.DictationPanel();app.read_status=lambda:{'phase':phase[0]}
    assert app.register(None);app.activate();app.live_toggle.set_active(True);app.preview_toggle.set_active(a.previews)
    app.original.grab_focus();pump(.5)
    def real_review(text,mode,language):
        t=time.monotonic();phase_at_start=phase[0];error=None;proposal=None
        try:
            assert mode=='grammar' and language=='English'
            code="import json,sys;sys.path.insert(0,sys.argv[1]);from dictation_review import review;print(json.dumps({'proposal':review(**json.load(sys.stdin))}))"
            env=dict(os.environ,DBUS_SESSION_BUS_ADDRESS=os.environ['MSERIES_REVIEW_OWNER_BUS'])
            response=subprocess.run(['/usr/bin/python3','-c',code,str(source)],input=json.dumps({'text':text,'mode':mode,'language':language}),
                capture_output=True,text=True,timeout=95,env=env)
            if response.returncode:raise ReviewUnavailable('Existing quiet-gated4B review unavailable')
            proposal=json.loads(response.stdout)['proposal']
            return proposal
        except Exception as e:error=type(e).__name__;raise
        finally:
            report['model_stages'].append({'source':text,'mode':mode,'language':language,'proposal':proposal,'error':error,'started_s':t-started,'elapsed_s':time.monotonic()-t,'speech_phase_at_start':phase_at_start})
    app.review=real_review
    def shown(buffer):
        report['proposal_events'].append({'wall_s':time.monotonic()-started,'text':app.text(app.proposed),'speech_phase':phase[0]})
    app.proposed.get_buffer().connect('changed',shown)
    env=dict(os.environ,TRANSCRIBE_LIBRARY=str(Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'),OMP_NUM_THREADS='4',OPENBLAS_NUM_THREADS='1')
    started=time.monotonic()
    asr=subprocess.Popen([str(Path.home()/'.local/share/mseries/stream/venv/bin/python'),'-u',str(source/'english-workflow-smoke.py'),*sys.argv[1:],'--asr-worker'],
        stdout=subprocess.PIPE,text=True,stderr=(root/'private-asr.log').open('w'),env=env,start_new_session=True)
    def reader():
        for line in asr.stdout:
            row=json.loads(line)
            def update(row=row):
                if stop.is_set():return False
                app.original.get_buffer().set_text(row['text']);report['source_events'].append({**row,'widget_wall_s':time.monotonic()-started})
                if row['final']:phase[0]='ready'
                app.poll();return False
            GLib.idle_add(update)
    threading.Thread(target=reader,daemon=True).start()
    until(lambda:asr.poll() is not None and phase[0]=='ready',100)
    assert asr.returncode==0
    until(lambda:not app.busy and app.live.finalized,110)
    report.update(complete=True,passed=True,original_preserved=app.text(app.original)==report['source_events'][-1]['text'],
        first_original_s=next(e['widget_wall_s'] for e in report['source_events'] if e['text']),
        first_suggestion_s=next(e['wall_s'] for e in report['proposal_events'] if e['text']),
        english_suggestion_visible_during_speech=any(e['text'] and e['speech_phase']=='listening' for e in report['proposal_events']),
        final_proposal=app.text(app.proposed),copy_enabled=app.copy.get_sensitive())
    assert (not a.previews or report['english_suggestion_visible_during_speech']) and report['original_preserved'] and report['copy_enabled']
    assert any(s['mode']=='grammar' and s['speech_phase_at_start']=='ready' for s in report['model_stages'])
    assert bench.metadata()==identity
except Exception as error:
    report['failure_kind']=type(error).__name__;report['quality_score']=None if report.get('interruption') else False
    raise
finally:
    stop.set()
    if samples:report['resources']={'samples':len(samples),'min_available_bytes':min(s['available_bytes'] for s in samples),'max_fan_rpm':max(max(s['fans_rpm'].values(),default=9999) for s in samples),'max_temp_c':max(max(s['temperatures_c'].values(),default=999) for s in samples)}
    checkpoint()
    for child in [asr,cpu]:
        if child and child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try:child.wait(3)
            except subprocess.TimeoutExpired:os.killpg(child.pid,signal.SIGKILL);child.wait()
    if app:app.window.close();app.quit()
