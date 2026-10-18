#!/usr/bin/python3
"""Explicit English conversation window; F5 supplies text through normal input."""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from dictation_voice import VoiceSession, VoiceUnavailable, VoiceCancelled, F5ReplyGate


def qualification(args):
    """File-only text → existing LLM → English WAV; never plays or captures audio."""
    if not args.output or not args.wav_dir:
        raise SystemExit('--qualification requires --output and --wav-dir (new private directory)')
    result = {'schema': 1, 'case': 'synthetic-English-voice-reply', 'microphone': False,
              'playback': False, 'tools': False, 'completed': False}
    try:
        result.update(VoiceSession().run(args.text, speak=False, wav_dir=args.wav_dir))
    except Exception as error:
        result.update(error_kind=type(error).__name__, error=str(error)[:200])
    target = Path(args.output)
    # Refuse overwrite/symlink publication accidents; receipts are private by default.
    fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w') as stream: json.dump(result, stream, indent=2)
    return 0 if result['completed'] else 1


def application_class():
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gio, GLib, Gtk, Gdk
    from dictation_status import read_status

    class VoiceAssistant(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='org.techmore.VoiceAssistant', flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
            self.window = None
            self.closed = False
            self.session = None
            self.generation = 0
            self.phase = 'unavailable'
            self.gate = F5ReplyGate()

        def do_activate(self):
            if self.window:
                self.window.present(); return
            self.window = Gtk.ApplicationWindow(application=self, title='English Voice Assistant')
            self.window.set_default_size(660, 560)
            self.window.set_titlebar(Gtk.HeaderBar())
            self.window.connect('close-request', self.close)
            keys = Gtk.EventControllerKey()
            keys.connect('key-pressed', self.key_pressed)
            self.window.add_controller(keys)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            for side in ('top', 'bottom', 'start', 'end'): getattr(box, 'set_margin_' + side)(18)
            self.window.set_child(box)
            title = Gtk.Label(label='English voice replies', xalign=0)
            title.add_css_class('title-2'); box.append(title)
            box.append(Gtk.Label(label='Focus your English question and use F5. English words appear as you speak. Ask local assistant reads its answer aloud using a lightweight robotic English voice.', wrap=True, xalign=0))
            focus = Gtk.Button(label='Focus question for F5')
            focus.set_focus_on_click(False)
            focus.connect('clicked', lambda *_: self.original.grab_focus()); box.append(focus)
            self.original = self.editor(box, 'Your English question — preserved', True)
            self.original.get_buffer().connect('changed', self.changed)
            self.automatic = Gtk.CheckButton(label='Reply aloud after F5')
            self.automatic.set_active(False)
            self.automatic.set_tooltip_text('Optional. Only a new dictation completed in this focused question starts a reply. No background listening.')
            self.automatic.connect('toggled', self.option_changed); box.append(self.automatic)
            buttons = Gtk.Box(spacing=12)
            self.ask = Gtk.Button(label='Ask local assistant')
            self.ask.connect('clicked', self.start); buttons.append(self.ask)
            self.cancel_button = Gtk.Button(label='Cancel reply')
            self.cancel_button.connect('clicked', lambda *_: self.cancel()); buttons.append(self.cancel_button)
            box.append(buttons)
            self.reply = self.editor(box, 'English reply', False)
            self.message = Gtk.Label(label='No tools or desktop actions. Uses the existing everyday model and waits for memory and cooling headroom.', wrap=True, xalign=0)
            box.append(self.message)
            self.poll(); self.timer = GLib.timeout_add(250, self.poll)
            self.window.present()

        @staticmethod
        def editor(box, caption, editable):
            box.append(Gtk.Label(label=caption, xalign=0))
            view = Gtk.TextView(editable=editable, wrap_mode=Gtk.WrapMode.WORD_CHAR)
            for side in ('top', 'bottom', 'left', 'right'): getattr(view, 'set_' + side + '_margin')(8)
            scroll = Gtk.ScrolledWindow(min_content_height=120, vexpand=True)
            scroll.set_has_frame(True); scroll.set_child(view); box.append(scroll)
            return view

        @staticmethod
        def text(view):
            buffer = view.get_buffer()
            return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

        def key_pressed(self, _controller, keyval, _keycode, _state):
            if keyval == Gdk.KEY_Escape:
                self.cancel(); return True
            return False

        def changed(self, *_):
            if self.session:
                self.cancel('Question changed. Previous reply text is preserved.')

        def option_changed(self, *_):
            self.gate.eligible = False
            if not self.automatic.get_active(): self.cancel('Automatic spoken replies are off.')

        def cancel(self, message='Voice reply cancelled. Original question and reply text are preserved.'):
            self.generation += 1
            if self.session: self.session.cancel()
            self.session = None
            if hasattr(self, 'message'): self.message.set_label(message)

        def poll(self):
            if self.closed: return False
            row = read_status()
            live = False
            if row and row['updated_at'] <= time.time() + 5:
                try: os.kill(row['pid'], 0); live = True
                except OSError: pass
            phase = row['phase'] if live else 'unavailable'
            recording = phase in ('loading', 'listening', 'finishing')
            focused = self.window.get_focus() == self.original
            if recording and self.phase not in ('loading', 'listening', 'finishing'):
                self.cancel('F5 dictation in progress. English question is preserved.')
            source = self.gate.observe(phase, focused, self.automatic.get_active(), self.text(self.original))
            self.phase = phase
            self.ask.set_sensitive(not recording)
            self.cancel_button.set_sensitive(self.session is not None)
            if source is not None: self.start()
            return True

        def start(self, *_):
            if self.phase in ('loading', 'listening', 'finishing'): return
            self.cancel('Preparing a short English reply locally…')
            source = self.text(self.original)
            session = self.session = VoiceSession()
            generation = self.generation
            self.reply.get_buffer().set_text('')
            def update(text):
                def show():
                    if not self.closed and generation == self.generation:
                        self.reply.get_buffer().set_text(text)
                    return False
                GLib.idle_add(show)
            def work():
                try:
                    result = session.run(source, on_text=update, speak=True)
                    message = ('English reply complete.' if result['finish_reason'] == 'stop'
                               else 'Reply reached its length limit. English text is preserved.')
                except VoiceCancelled:
                    message = 'Voice reply cancelled. English text is preserved.'
                except VoiceUnavailable as error:
                    message = str(error)
                except Exception:
                    message = 'Local voice reply is unavailable. English text is preserved.'
                def finish():
                    if not self.closed and generation == self.generation:
                        self.session = None; self.message.set_label(message)
                    return False
                GLib.idle_add(finish)
            threading.Thread(target=work, daemon=True).start()

        def close(self, *_):
            self.closed = True
            self.cancel()
            if getattr(self, 'timer', None): GLib.source_remove(self.timer)
            return False

    return VoiceAssistant


def desktop():
    return application_class()().run()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qualification', action='store_true', help='File-only synthetic test; no capture or playback')
    parser.add_argument('--text', default='In one short English sentence, say that local voice replies are ready for testing.')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--wav-dir', type=Path)
    args = parser.parse_args()
    raise SystemExit(qualification(args) if args.qualification else desktop())
