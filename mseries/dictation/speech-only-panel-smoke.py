#!/usr/bin/python3
"""Private GTK4 STT-only wiring; synthetic text/status, no microphone or models.

Use --default-review to run the existing grammar-panel smoke in the same private
display/bus/home isolation with the speech-only environment flag explicitly off.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time


def isolated(default_review):
    with tempfile.TemporaryDirectory(prefix='mseries-speech-only-panel-') as directory:
        root = Path(directory)
        env = dict(os.environ)
        for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                    'AT_SPI_BUS_ADDRESS', 'IBUS_ADDRESS'):
            env.pop(key, None)
        for variable, name in [('HOME', 'home'), ('XDG_RUNTIME_DIR', 'runtime'),
                               ('XDG_CONFIG_HOME', 'config'), ('XDG_CACHE_HOME', 'cache'),
                               ('XDG_DATA_HOME', 'data'), ('XDG_STATE_HOME', 'state')]:
            path = root / name
            path.mkdir(mode=0o700)
            env[variable] = str(path)
        env.update(MSERIES_SPEECH_PANEL_TEST='1', MSERIES_INPUT_TEST_SESSION='1',
                   GSETTINGS_BACKEND='memory', GSK_RENDERER='cairo', GDK_BACKEND='x11',
                   NO_AT_BRIDGE='1', GTK_A11Y='none', GTK_USE_PORTAL='0', GIO_USE_VFS='local')
        if default_review:
            env.pop('MSERIES_DICTATION_SPEECH_ONLY', None)
            script = Path(__file__).with_name('panel-smoke.py')
        else:
            env['MSERIES_DICTATION_SPEECH_ONLY'] = '1'
            script = Path(__file__).resolve()
        config = root / 'session.conf'
        config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                          '<auth>EXTERNAL</auth><policy context="default">'
                          '<allow send_destination="*"/><allow receive_sender="*"/>'
                          '<allow own="*"/></policy></busconfig>')
        return subprocess.run(['dbus-run-session', '--config-file=' + str(config), '--',
                               'xvfb-run', '-a', sys.executable, str(script)], env=env,
                              timeout=30).returncode


def main():
    default_review = sys.argv[1:] == ['--default-review']
    if sys.argv[1:] and not default_review:
        raise SystemExit('Use no arguments or --default-review')
    if os.environ.get('MSERIES_SPEECH_PANEL_TEST') != '1' or default_review:
        return isolated(default_review)
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import GLib, Gtk
    spec = importlib.util.spec_from_file_location('speech_only_panel', Path(__file__).with_name('dictation-panel.py'))
    panel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panel)
    app = panel.DictationPanel()
    phase = ['ready']
    calls = []
    app.read_status = lambda: {'phase': phase[0]}
    def forbidden_review(*args):
        calls.append(args)
        raise AssertionError('Speech-only panel tried to invoke a language model')
    class ForbiddenLive:
        def observe(self, *_):
            raise AssertionError('Speech-only panel entered the review scheduler')
        def take(self, *_):
            raise AssertionError('Speech-only panel requested a review')
    app.review = forbidden_review
    app.live = ForbiddenLive()
    assert app.register(None)
    app.activate()
    def settle():
        until = time.monotonic() + .04
        while time.monotonic() < until:
            while GLib.MainContext.default().pending():
                GLib.MainContext.default().iteration(False)
            time.sleep(.005)
    def descendants(widget):
        yield widget
        child = widget.get_first_child()
        while child:
            yield from descendants(child)
            child = child.get_next_sibling()
    try:
        assert app.speech_only
        assert app.original.get_editable() and app.original.get_visible()
        assert app.state.get_visible() and app.record.get_visible()
        assert 'Original English transcript' in [w.get_label() for w in descendants(app.window) if isinstance(w, Gtk.Label)]
        for control in ('live_toggle', 'preview_toggle', 'transform', 'proposed', 'copy'):
            assert not hasattr(app, control), 'Speech-only mode constructed review control: ' + control
        assert not any(isinstance(w, Gtk.CheckButton) for w in descendants(app.window))
        assert [w.get_label() for w in descendants(app.window) if isinstance(w, Gtk.Button) and w.get_label()] == ['Focus transcript for F5']
        app.record.emit('clicked')
        assert app.window.get_focus() == app.original
        source = 'These are my original English words.\nKeep 42, punctuation, and literal "review this" unchanged.'
        app.original.get_buffer().set_text('These are my')
        for current in ('loading', 'listening', 'finishing', 'ready'):
            phase[0] = current
            app.poll()
            assert app.record.get_sensitive() == (current == 'ready')
            app.original.get_buffer().set_text(source)
            app.start_review()
            app.launch_review(source)
            app.show_proposal(source, 'MUST NOT replace anything', True)
            app.observe_live()
            app.flush_changed()
            settle()
            assert app.text(app.original) == source and not app.busy
            assert not getattr(app, 'edit_id', None)
        for current in ('error', 'waiting', 'cancelled', 'stopped', 'unavailable', 'ready'):
            phase[0] = current
            app.poll()
            assert app.record.get_sensitive() and app.state.get_label()
            assert app.text(app.original) == source
        # Exercise more than one status timer tick after a completed dictation.
        until = time.monotonic() + 1.1
        while time.monotonic() < until:
            settle()
        assert calls == [] and app.text(app.original) == source and not app.busy
        app.window.close()
        assert app.closed and not app.poll()
        app.start_review()
        app.launch_review(source)
        assert calls == []
        print(json.dumps({'passed': True, 'native_gtk4_speech_only_panel': True,
                          'speech_only_environment_flag': True, 'original_transcript_preserved': True,
                          'focus_and_status_controls': True, 'review_controls_absent': True,
                          'capture_finalization_no_review': True, 'programmatic_review_blocked': True,
                          'status_timer_no_review': True, 'model_inference': False,
                          'microphone_recorded': False, 'owner_windows_opened': False,
                          'dictation_panel_sha256': hashlib.sha256(Path(__file__).with_name('dictation-panel.py').read_bytes()).hexdigest()}))
    finally:
        if not app.closed:
            app.window.close()
        app.quit()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
