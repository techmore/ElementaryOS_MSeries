#!/usr/bin/python3
"""Private GTK4 English-only panel wiring. Synthetic reviewer, no audio/models."""
import importlib.util,json,os,subprocess,sys,threading,time
from pathlib import Path
if os.environ.get('MSERIES_INPUT_TEST_SESSION')!='1':
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env','MSERIES_INPUT_TEST_SESSION=1',
        'GSETTINGS_BACKEND=memory','GSK_RENDERER=cairo','GDK_BACKEND=x11',sys.executable,str(Path(__file__).resolve())]).returncode)
from gi.repository import GLib
from dictation_review import ReviewUnavailable
spec=importlib.util.spec_from_file_location('english_panel',Path(__file__).with_name('dictation-panel.py'));panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
app=panel.DictationPanel();phase=['ready'];app.read_status=lambda:{'phase':phase[0]}
assert app.register(None);app.activate()
def pump(condition):
    deadline=time.monotonic()+5
    while not condition():
        assert time.monotonic()<deadline,'UI callback timed out'
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.01)
try:
    seen=[]
    def review(source,mode,language):seen.append((source,mode,language));return 'We were late.'
    app.review=review;app.original.get_buffer().set_text('we was late');app.start_review();pump(lambda:not app.busy)
    assert app.text(app.original)=='we was late' and app.text(app.proposed)=='We were late.' and app.copy.get_sensitive()
    assert seen==[('we was late','grammar','English')]
    gate=threading.Event();app.review=lambda *_:gate.wait(3) and 'stale'
    app.start_review();app.original.get_buffer().set_text('new original');gate.set();pump(lambda:not app.busy)
    assert not app.copy.get_sensitive() and 'changed' in app.message.get_label()
    app.review=lambda *_:(_ for _ in ()).throw(ReviewUnavailable('Waiting for headroom'))
    app.start_review();pump(lambda:not app.busy);assert app.message.get_label()=='Waiting for headroom'
    for p in ['error','waiting','cancelled','stopped','unavailable','ready']:
        phase[0]=p;app.poll();assert app.record.get_sensitive();app.proposed.grab_focus();app.record.emit('clicked');assert app.window.get_focus()==app.original
    for p in ['loading','listening','finishing']:
        phase[0]=p;app.poll();assert not app.record.get_sensitive() and not app.transform.get_sensitive()
    from dictation_live import LiveEnglishReview
    app.live=LiveEnglishReview();clock=[100.];app.clock=lambda:clock[0];app.original.get_buffer().set_text('')
    app.preview_toggle.set_active(True);app.original.grab_focus();phase[0]='listening'
    calls=[];entered=threading.Event();release=threading.Event()
    def reviewer(source,mode,language):
        calls.append((source,mode,language))
        if len(calls)==1:entered.set();assert release.wait(3)
        return 'We were' if source=='we was' else 'We were late.'
    app.review=reviewer;app.original.get_buffer().set_text('we was');app.poll();assert entered.wait(2)
    app.original.get_buffer().set_text('we was late');app.poll();assert len(calls)==1
    release.set();pump(lambda:not app.busy);assert app.text(app.proposed)=='We were' and not app.copy.get_sensitive(), repr((app.text(app.proposed),app.copy.get_sensitive(),calls,app.live.__dict__))
    clock[0]=103;app.poll();pump(lambda:not app.busy)
    assert app.text(app.proposed)=='We were late.' and not app.copy.get_sensitive()
    phase[0]='ready';app.poll();assert app.copy.get_sensitive() and len(calls)==2
    assert all(c[1:]==('grammar','English') for c in calls)
    assert not hasattr(app,'language') and not hasattr(app,'mode'),'English-only UI must not expose foreign translation controls'
    print(json.dumps({'passed':True,'native_gtk4_panel':True,'english_only':True,'original_preserved':True,
        'stale_proposal_discarded':True,'unavailable_preserves_original':True,'focus_retry_after_error_or_waiting':True,
        'live_english_preview':True,'latest_only_requests':True,'no_duplicate_final_review':True,'model_inference':False,
        'microphone_recorded':False,'owner_windows_opened':False}))
finally:app.window.close();app.quit()
