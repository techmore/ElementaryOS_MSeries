#!/usr/bin/python3
"""Native review UI wiring with synthetic transforms on a private Xvfb/bus; no models/mic."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

if os.environ.get('MSERIES_INPUT_TEST_SESSION') != '1':
    raise SystemExit(subprocess.run(['dbus-run-session','--','xvfb-run','-a','env',
        'MSERIES_INPUT_TEST_SESSION=1','GSETTINGS_BACKEND=memory','GSK_RENDERER=cairo',
        'GDK_BACKEND=x11',sys.executable,str(Path(__file__).resolve())]).returncode)
assert os.environ.get('GSETTINGS_BACKEND')=='memory'
from gi.repository import GLib
spec=importlib.util.spec_from_file_location('dictation_panel',Path(__file__).with_name('dictation-panel.py'))
panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
from dictation_review import ReviewUnavailable
app=panel.DictationPanel();app.read_status=lambda: {'phase':'ready'}
assert app.register(None);app.activate()
def pump_until(condition):
    deadline=time.monotonic()+5
    while not condition():
        assert time.monotonic()<deadline,'UI callback timed out'
        while GLib.MainContext.default().pending():GLib.MainContext.default().iteration(False)
        time.sleep(.01)
try:
    app.original.get_buffer().set_text('we was not meeting at 14:30')
    seen=[]
    def transform(source,mode,language):
        seen.append((source,mode,language));return 'We were not meeting at 14:30.'
    app.review=transform;app.start_review();pump_until(lambda: not app.busy)
    assert app.text(app.proposed)=='We were not meeting at 14:30.'
    assert app.text(app.original)=='we was not meeting at 14:30'
    assert app.copy.get_sensitive()
    app.language.set_selected(1);app.mode.set_selected(1)
    assert not app.text(app.proposed) and not app.copy.get_sensitive()
    app.start_review();pump_until(lambda: not app.busy)
    assert seen[-1][1:]==('translate','French')
    app.mode.set_selected(2)
    stages=[]
    def pipeline_stage(source,mode,language):
        stages.append((source,mode,language))
        return 'translated source' if mode=='translate' else 'polished translation'
    app.review=pipeline_stage;app.start_review();pump_until(lambda:not app.busy)
    assert app.text(app.proposed)=='polished translation'
    assert app.text(app.intermediate_text)=='translated source' and app.intermediate.get_visible()
    assert stages[-1]==('translated source','grammar','French')
    def interrupted_polish(source,mode,language):
        if mode=='grammar':raise ReviewUnavailable('waiting')
        return 'available translation'
    app.review=interrupted_polish;app.start_review();pump_until(lambda:not app.busy)
    assert app.text(app.proposed)=='available translation' and 'retained' in app.message.get_label()
    def unavailable_translation(*_):raise ReviewUnavailable('waiting')
    app.review=unavailable_translation;app.start_review();pump_until(lambda:not app.busy)
    assert not app.text(app.proposed) and not app.copy.get_sensitive()
    assert not app.intermediate.get_visible() and not app.text(app.intermediate_text)
    app.mode.set_selected(1)
    gate=threading.Event()
    app.review=lambda *_: gate.wait(3) and 'stale'
    app.start_review();app.original.get_buffer().set_text('new original');gate.set()
    pump_until(lambda: not app.busy)
    assert not app.text(app.proposed) and 'changed' in app.message.get_label()
    def unavailable(*_):raise ReviewUnavailable('Waiting for headroom')
    app.review=unavailable;app.start_review();pump_until(lambda: not app.busy)
    assert app.text(app.original)=='new original' and not app.copy.get_sensitive()
    assert app.message.get_label()=='Waiting for headroom'
    app.read_status=lambda:{'phase':'listening'};app.poll();before=len(seen);app.start_review()
    assert not app.transform.get_sensitive() and len(seen)==before
    for phase in ['error','waiting','stopped','unavailable','ready']:
        app.read_status=lambda phase=phase:{'phase':phase};app.poll()
        assert app.record.get_sensitive(),'Focus action must remain available after field refusal or waiting'
        app.proposed.grab_focus();app.record.emit('clicked')
        assert app.window.get_focus()==app.original,'Retry action did not focus the original transcript'
    for phase in ['loading','listening','finishing']:
        app.read_status=lambda phase=phase:{'phase':phase};app.poll()
        assert not app.record.get_sensitive(),'Do not redirect focus during active speech preparation or capture'
    print(json.dumps({'passed':True,'native_gtk4_panel':True,'original_preserved':True,
        'mode_language_wiring':True,'stale_proposal_discarded':True,'unavailable_preserves_original':True,
        'review_blocked_while_listening':True,'translate_then_grammar_wiring':True,'partial_pipeline_preserves_translation':True,'model_inference':False,'microphone_recorded':False,
        'owner_windows_opened':False,'focus_retry_after_error_or_waiting':True,'scope':'UI wiring with synthetic transforms; no grammar or translation quality claim'}))
finally:
    app.window.close();app.quit()
