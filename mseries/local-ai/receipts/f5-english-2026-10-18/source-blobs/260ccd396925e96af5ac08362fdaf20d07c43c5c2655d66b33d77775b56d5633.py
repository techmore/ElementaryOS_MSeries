#!/usr/bin/python3
"""Private native GTK4 voice wiring; synthetic sessions, no inference or sound."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time


def main():
    if os.environ.get('MSERIES_VOICE_PANEL_TEST') != '1':
        with tempfile.TemporaryDirectory(prefix='mseries-voice-panel-') as directory:
            root = Path(directory)
            env = dict(os.environ)
            for key in ('DISPLAY', 'WAYLAND_DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS',
                        'AT_SPI_BUS_ADDRESS', 'IBUS_ADDRESS'):
                env.pop(key, None)
            for variable, name in [('XDG_RUNTIME_DIR', 'runtime'), ('XDG_CONFIG_HOME', 'config'),
                                   ('XDG_CACHE_HOME', 'cache'), ('XDG_DATA_HOME', 'data'),
                                   ('XDG_STATE_HOME', 'state')]:
                path = root / name; path.mkdir(mode=0o700); env[variable] = str(path)
            env.update(MSERIES_VOICE_PANEL_TEST='1', GSETTINGS_BACKEND='memory',
                       GSK_RENDERER='cairo', GDK_BACKEND='x11', NO_AT_BRIDGE='1',
                       GTK_A11Y='none', GTK_USE_PORTAL='0', GIO_USE_VFS='local')
            config = root / 'session.conf'
            config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                              '<auth>EXTERNAL</auth><policy context="default">'
                              '<allow send_destination="*"/><allow receive_sender="*"/>'
                              '<allow own="*"/></policy></busconfig>')
            return subprocess.run(['dbus-run-session', '--config-file=' + str(config), '--', 'xvfb-run', '-a', sys.executable,
                                   str(Path(__file__).resolve())], env=env).returncode
    import gi
    gi.require_version('Gtk', '4.0')
    gi.require_version('Gdk', '4.0')
    from gi.repository import GLib, Gdk
    from unittest.mock import patch
    import dictation_status
    from dictation_voice import VoiceCancelled
    spec = importlib.util.spec_from_file_location('voice_panel', Path(__file__).with_name('voice-assistant.py'))
    panel = importlib.util.module_from_spec(spec); spec.loader.exec_module(panel)
    phase = ['ready']
    instances = []
    class SyntheticSession:
        def __init__(self):
            self.entered = threading.Event()
            self.release = threading.Event()
            self.cancelled = False
            self.exited = threading.Event()
            instances.append(self)
        def run(self, source, *, on_text, speak):
            self.source, self.speak = source, speak
            self.entered.set()
            on_text('A partial English reply.')
            try:
                assert self.release.wait(5), 'synthetic request was not released or cancelled'
                if self.cancelled:
                    # Deliberate obsolete callback proves generation rejection.
                    on_text('STALE cancelled reply')
                    raise VoiceCancelled('Synthetic cancellation')
                on_text('The final English reply.')
                return {'finish_reason': 'stop'}
            finally:
                self.exited.set()
        def cancel(self):
            self.cancelled = True; self.release.set()
    panel.VoiceSession = SyntheticSession
    def status(): return {'phase': phase[0], 'pid': os.getpid(), 'updated_at': time.time()}
    with patch.object(dictation_status, 'read_status', status):
        app = panel.application_class()()
    assert app.register(None); app.activate()
    def pump(condition, timeout=5):
        deadline = time.monotonic() + timeout
        while True:
            while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
            if condition(): return
            assert time.monotonic() < deadline, 'private GTK callback timed out'
            time.sleep(.005)
    def settle():
        until = time.monotonic() + .05
        pump(lambda: time.monotonic() >= until)
    def begin(source):
        app.original.get_buffer().set_text(source)
        app.ask.emit('clicked')
        session = instances[-1]
        pump(lambda: session.entered.is_set() and app.text(app.reply) == 'A partial English reply.')
        assert session.source == source and session.speak
        return session
    try:
        assert not app.automatic.get_active(), 'automatic speech must start OFF'
        assert app.original.get_editable() and not app.reply.get_editable()
        assert 'English' in app.window.get_title()
        assert not hasattr(app, 'language') and not hasattr(app, 'mode')
        app.original.grab_focus()
        phase[0] = 'listening'; app.poll()
        assert not app.ask.get_sensitive()
        app.original.get_buffer().set_text('Synthetic F5 question with automatic replies off.')
        phase[0] = 'ready'; app.poll(); settle()
        assert instances == [], 'default-off F5 must not ask or speak'

        session = begin('Synthetic explicit English question.')
        assert app.text(app.original) == session.source
        session.release.set(); pump(lambda: app.session is None)
        assert app.text(app.reply) == 'The final English reply.'
        assert app.text(app.original) == session.source

        session = begin('Synthetic cancellation question.')
        original = app.text(app.original)
        app.cancel_button.emit('clicked'); pump(session.exited.is_set); settle()
        assert session.cancelled and app.text(app.original) == original
        assert app.text(app.reply) == 'A partial English reply.', 'obsolete callback overwrote visible reply'

        session = begin('Synthetic edit question.')
        app.original.get_buffer().set_text('New English question preserved.')
        pump(session.exited.is_set); settle()
        assert session.cancelled and app.text(app.original) == 'New English question preserved.'
        assert app.text(app.reply) == 'A partial English reply.'

        session = begin('Synthetic new-capture question.')
        phase[0] = 'listening'; app.poll()
        pump(session.exited.is_set); settle()
        assert session.cancelled
        phase[0] = 'cancelled'; app.poll()
        assert app.text(app.original) == 'Synthetic new-capture question.'

        phase[0] = 'ready'; app.poll()
        app.automatic.set_active(True)
        app.original.get_buffer().set_text('')
        app.original.grab_focus(); phase[0] = 'listening'; app.poll()
        app.original.get_buffer().set_text('Synthetic automatic English question.')
        phase[0] = 'finishing'; app.poll()
        count = len(instances)
        phase[0] = 'ready'; app.poll()
        pump(lambda: len(instances) == count + 1 and instances[-1].entered.is_set())
        session = instances[-1]
        assert session.source == 'Synthetic automatic English question.'
        app.poll(); assert len(instances) == count + 1, 'ready polling duplicated the reply'
        session.release.set(); pump(lambda: app.session is None)
        assert app.text(app.original) == session.source

        count = len(instances)
        app.original.grab_focus(); phase[0] = 'listening'; app.poll()
        app.original.get_buffer().set_text('Synthetic cancelled F5 question.')
        phase[0] = 'cancelled'; app.poll()
        phase[0] = 'ready'; app.poll(); settle()
        assert len(instances) == count, 'cancelled F5 must not produce a reply'

        app.original.grab_focus(); phase[0] = 'listening'; app.poll()
        app.original.get_buffer().set_text('Synthetic focus loss question.')
        app.reply.grab_focus(); app.poll()
        app.original.grab_focus(); phase[0] = 'ready'; app.poll(); settle()
        assert len(instances) == count, 'focus loss must disarm automatic reply'

        session = begin('Synthetic Escape cancellation.')
        assert app.key_pressed(None, Gdk.KEY_Escape, 0, 0)
        pump(session.exited.is_set); settle(); assert session.cancelled
        session = begin('Synthetic window-close question.')
        original = app.text(app.original)
        app.window.close(); pump(session.exited.is_set); settle()
        assert session.cancelled and app.closed and app.text(app.original) == original
        assert all(instance.exited.is_set() for instance in instances)
        print(json.dumps({'passed': True, 'native_gtk4': True, 'english_only': True,
                          'automatic_reply_default_off': True, 'explicit_ask': True,
                          'partial_and_final_reply': True, 'original_preserved': True,
                          'cancel_button': True, 'edit_cancels': True, 'new_capture_cancels': True,
                          'focused_f5_completion_only': True, 'no_duplicate_ready_reply': True,
                          'escape_and_window_close_cancel': True, 'stale_callback_rejected': True,
                          'model_inference': False, 'tts_inference': False, 'audio_playback': False,
                          'microphone_recorded': False, 'owner_windows_opened': False}))
    finally:
        for instance in instances: instance.cancel()
        if not app.closed: app.window.close()
        app.quit()
    return 0


if __name__ == '__main__': raise SystemExit(main())
