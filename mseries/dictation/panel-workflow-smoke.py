#!/usr/bin/python3
"""Public-file ASR → private GTK panel → English grammar → private clipboard."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--receipt-dir',type=Path,required=True)
parser.add_argument('--wav',type=Path,default=Path.home()/'.local/share/mseries/stream/libri.wav')
args=parser.parse_args()
HERE=Path(__file__).resolve().parent
if os.environ.get('MSERIES_PANEL_WORKFLOW_SESSION')!='1':
    owner_bus=os.environ.get('DBUS_SESSION_BUS_ADDRESS','unix:path=/run/user/'+str(os.getuid())+'/bus')
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env',
        'MSERIES_PANEL_WORKFLOW_SESSION=1','MSERIES_INPUT_TEST_SESSION=1','GSETTINGS_BACKEND=memory',
        'MSERIES_REVIEW_OWNER_BUS='+owner_bus,sys.executable,str(Path(__file__).resolve()),*sys.argv[1:]]).returncode)
assert os.environ.get('GSETTINGS_BACKEND')=='memory'
output=args.receipt_dir.resolve();output.mkdir(parents=True,mode=0o700,exist_ok=False)
frozen=output/'evaluated-source';source=frozen/'dictation';source.mkdir(parents=True);(frozen/'local-ai').mkdir()
for name in ['stream-dictate.py','dictation-input.py','dictation-input-client.py','dictation-panel.py',
             'dictation_review.py','dictation_live.py','dictation_pipeline.py','dictation_resources.py','dictation_status.py','dictation_model.py',
             'review-smoke.py','panel-workflow-smoke.py']:
    (source/name).write_bytes((HERE/name).read_bytes())
(frozen/'local-ai/machine.py').write_bytes((HERE.parent/'local-ai/machine.py').read_bytes())
source_hashes={p.relative_to(frozen).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in frozen.rglob('*.py')}
sys.path.insert(0,str(source));sys.path.insert(0,str(frozen/'local-ai'))
from dictation_resources import snapshot,reasons
spec=importlib.util.spec_from_file_location('panel_workflow_admission',source/'review-smoke.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
identity=bench.metadata();bench.wait_ready(False,identity)
report={'complete':False,'passed':False,'source_sha256':source_hashes,'runtime':identity,
        'microphone_recorded':False,'keyboard_device_opened':False,'owner_windows_opened':False,
        'method':'Existing public WAV, private Xvfb/IBus/GTK4 panel and clipboard, single existing supervised local model',
        'model_stages':[]}
samples=[];next_sample=0

def checkpoint():
    temp=output/'receipt.tmp';temp.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n');temp.chmod(0o600)
    os.replace(temp,output/'receipt.json')

checkpoint()
with tempfile.TemporaryDirectory(prefix='mseries-panel-workflow-') as directory:
    os.environ.update(IBUS_ADDRESS='unix:path='+directory+'/bus',GTK_IM_MODULE='ibus',GDK_BACKEND='x11',
        XDG_CACHE_HOME=directory+'/cache',XDG_CONFIG_HOME=directory+'/config',
        GTK_A11Y='atspi',GIO_USE_VFS='local',GSK_RENDERER='cairo',LIBGL_ALWAYS_SOFTWARE='1')
    import gi
    gi.require_version('IBus','1.0');gi.require_version('Gtk','4.0');gi.require_version('Gdk','4.0')
    from gi.repository import IBus,GLib,Gdk
    daemon=engine=asr=None;app=None
    def measure():
        global next_sample
        if time.monotonic()>=next_sample:
            s=snapshot();samples.append(s);next_sample=time.monotonic()+1
            if reasons(identity['policy'],sample=s):raise RuntimeError('Resource policy interrupted the owned workflow')
    def pump(seconds=.1):
        until=time.monotonic()+seconds
        while time.monotonic()<until:
            while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
            measure();time.sleep(.01)
    def until(condition,timeout=100):
        deadline=time.monotonic()+timeout
        while not condition():
            if time.monotonic()>deadline:raise TimeoutError('Owned workflow stage timed out')
            pump()
    try:
        daemon=subprocess.Popen(['ibus-daemon','--single','--emoji-extension','disable',
            '--address',os.environ['IBUS_ADDRESS'],'--cache','none'])
        time.sleep(1);IBus.init()
        engine=subprocess.Popen(['/usr/bin/python3',str(source/'dictation-input.py')]);pump(1)
        subprocess.run(['/usr/bin/python3',str(source/'dictation-input-client.py'),'select','xkb:us::eng'],check=True)
        spec=importlib.util.spec_from_file_location('panel_workflow_ui',source/'dictation-panel.py')
        panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
        app=panel.DictationPanel();phase=['listening'];app.read_status=lambda:{'phase':phase[0]}
        assert app.register(None);app.activate();app.live_toggle.set_active(False);pump()
        app.window.get_surface().focus(Gdk.CURRENT_TIME);app.original.grab_focus();pump(1)
        assert not app.transform.get_sensitive()
        env=dict(os.environ,STREAM_OUTPUT='ibus',STREAM_TEST_INSERT='1',STREAM_TEST_WAV=str(args.wav.resolve()),
                 STREAM_BACKEND='cpu',STREAM_THREADS='6',STREAM_QUIET='1')
        for name in ['STREAM_KEEP','STREAM_DRY','STREAM_TEST_RAW']:env.pop(name,None)
        native=Path.home()/'.local/share/mseries/stream/native/transcribe-native-linux-aarch64-cpu-vulkan/libtranscribe.so'
        env['TRANSCRIBE_LIBRARY']=str(native)
        report['transcribe_library_sha256']=hashlib.sha256(native.read_bytes()).hexdigest()
        started=time.monotonic();first_text=None
        with (output/'private-asr.log').open('w') as log:
            asr=subprocess.Popen([str(Path.home()/'.local/share/mseries/stream/venv/bin/python'),'-I',
                str(source/'stream-dictate.py')],env=env,stdout=log,stderr=log,start_new_session=True)
            while asr.poll() is None:
                if time.monotonic()-started>90:raise TimeoutError('Owned ASR child timed out')
                if first_text is None and app.text(app.original):first_text=time.monotonic()-started
                pump()
            assert asr.returncode==0,'ASR-to-panel child failed; retain private log'
        assert 'using cpu backend (strict)' in (output/'private-asr.log').read_text()
        original=app.text(app.original)
        reference='He hoped there would be stew for dinner, turnips and carrots and bruised potatoes and fat mutton pieces to be ladled out in thick, peppered, flour-fattened sauce'
        actual=re.findall(r'\w+',original.casefold());expected=re.findall(r'\w+',reference.casefold())
        distance=list(range(len(actual)+1))
        for i,left in enumerate(expected,1):
            row=[i]
            for j,right in enumerate(actual,1):row.append(min(row[-1]+1,distance[j]+1,distance[j-1]+(left!=right)))
            distance=row
        wer=distance[-1]/len(expected)
        report['asr']={'completed':True,'normalized_word_error_rate':wer,'original_transcript':original,
            'wav_sha256':hashlib.sha256(args.wav.read_bytes()).hexdigest(),'first_widget_text_s':first_text,
            'elapsed_s':time.monotonic()-started,'backend':'cpu'}
        checkpoint();assert actual and wer<=.1,'ASR-to-panel reference check failed'
        phase[0]='ready';app.poll()
        def real_review(text,mode,language):
            started=time.monotonic()
            code="import json,sys;sys.path.insert(0,sys.argv[1]);from dictation_review import review;print(json.dumps({'proposal':review(**json.load(sys.stdin))},ensure_ascii=False))"
            child_env=dict(os.environ,DBUS_SESSION_BUS_ADDRESS=os.environ['MSERIES_REVIEW_OWNER_BUS'])
            process=subprocess.run(['/usr/bin/python3','-c',code,str(source)],input=json.dumps({'text':text,'mode':mode,'language':language}),
                text=True,capture_output=True,env=child_env,timeout=95)
            if process.returncode:
                from dictation_review import ReviewUnavailable
                raise ReviewUnavailable('Owned local review child unavailable; original retained')
            proposal=json.loads(process.stdout)['proposal']
            report['model_stages'].append({'mode':mode,'language':language,'synthetic_source':text,
                'proposal':proposal,'completed':True,'elapsed_s':time.monotonic()-started})
            checkpoint()
            return proposal
        app.review=real_review;app.start_review();until(lambda:not app.busy,200)
        assert len(report['model_stages'])==1,'English grammar review must complete'
        assert [(x['mode'],x['language']) for x in report['model_stages']]==[('grammar','English')]
        assert app.text(app.original)==original,'Original transcript changed'
        proposed=app.text(app.proposed);assert proposed==report['model_stages'][0]['proposal']
        assert app.copy.get_sensitive()
        app.copy.emit('clicked');copied=[]
        def got_clipboard(clipboard,result,*_):copied.append(clipboard.read_text_finish(result))
        app.window.get_clipboard().read_text_async(None,got_clipboard,None)
        until(lambda:bool(copied),5);assert copied[0]==proposed,'Private clipboard did not receive the reviewed proposal'
        assert bench.metadata()==identity,'Runtime changed during workflow'
        report.update(complete=True,passed=True,original_preserved=True,language='English',private_clipboard_matches=True,
            automatic_owner_app_insertion=False,quality_scope='Functional English client/pipeline check; inspect meaning separately')
    except Exception as error:
        report['failure_kind']=type(error).__name__
        report['failure_scope']='Inspect private harness log; retain completed stages and do not silently rescore/repeat'
        raise
    finally:
        if samples:
            report['resources']={'samples':len(samples),'min_available_bytes':min(x['available_bytes'] for x in samples),
                'max_fan_rpm':max(max(x['fans_rpm'].values(),default=9999) for x in samples),
                'max_temp_c':max(max(x['temperatures_c'].values(),default=999) for x in samples),
                'quiet_policy_passed':all(not reasons(identity['policy'],sample=x) for x in samples)}
        checkpoint()
        if asr and asr.poll() is None:
            os.killpg(asr.pid,signal.SIGTERM)
            try:asr.wait(timeout=5)
            except subprocess.TimeoutExpired:os.killpg(asr.pid,signal.SIGKILL);asr.wait()
        if app:app.window.close();app.quit()
        if engine:engine.terminate();engine.wait(timeout=5)
        if daemon:daemon.terminate();daemon.wait(timeout=5)
print(json.dumps({'passed':report['passed'],'complete':report['complete'],'model_stages':len(report['model_stages']),'microphone_recorded':False}))
