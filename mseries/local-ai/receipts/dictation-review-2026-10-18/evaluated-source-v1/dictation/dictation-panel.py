#!/usr/bin/python3
"""Native, opt-in F5 transcript review. Keeps original/proposal separate and ephemeral."""
import threading
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk
from dictation_review import LANGUAGES, ReviewUnavailable, review
from dictation_status import read_status


class DictationPanel(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.techmore.Dictation', flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        self.busy = False
        self.closed = False
        self.generation = 0
        self.review = review
        self.read_status = read_status

    def do_activate(self):
        if self.window:
            self.window.present(); return
        self.window = Gtk.ApplicationWindow(application=self, title='Dictation')
        self.window.set_default_size(660, 620)
        self.window.connect('close-request', self.close)
        self.window.set_titlebar(Gtk.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'bottom', 'start', 'end'): getattr(box, 'set_margin_' + side)(18)
        self.window.set_child(box)
        title = Gtk.Label(label='Speak, then review', xalign=0)
        title.add_css_class('title-2'); box.append(title)
        hint = Gtk.Label(label='Hold F5 in a text field. To review an utterance, focus the original transcript below, then hold F5 and speak.',
                         wrap=True, xalign=0)
        box.append(hint)
        self.record = Gtk.Button(label='Focus transcript for F5')
        self.record.set_focus_on_click(False)
        self.record.connect('clicked', lambda *_: self.original.grab_focus())
        box.append(self.record)
        self.state = Gtk.Label(label='', xalign=0, wrap=True); box.append(self.state)
        self.original = self.editor(box, 'Original transcript', editable=True)
        self.original.get_buffer().connect('changed', self.changed)
        controls = Gtk.Box(spacing=8)
        self.mode = Gtk.DropDown.new_from_strings(['Improve grammar', 'Translate'])
        self.language = Gtk.DropDown.new_from_strings(list(LANGUAGES))
        self.language.set_sensitive(False)
        self.mode.connect('notify::selected', lambda *_: self.language.set_sensitive(self.mode.get_selected() == 1))
        controls.append(self.mode); controls.append(self.language)
        self.transform = Gtk.Button(label='Review text')
        self.transform.connect('clicked', self.start_review); controls.append(self.transform); box.append(controls)
        self.proposed = self.editor(box, 'Proposed text — check meaning before copying', editable=False)
        self.copy = Gtk.Button(label='Copy proposed text')
        self.copy.set_sensitive(False)
        self.copy.connect('clicked', lambda *_: self.window.get_clipboard().set(self.text(self.proposed)))
        box.append(self.copy)
        self.message = Gtk.Label(label='Original text is never replaced automatically.', xalign=0, wrap=True)
        box.append(self.message)
        self.mode.connect('notify::selected', self.changed)
        self.language.connect('notify::selected', self.changed)
        self.poll()
        self.timer = GLib.timeout_add(500, self.poll)
        self.window.present()

    @staticmethod
    def editor(box, caption, editable):
        box.append(Gtk.Label(label=caption, xalign=0))
        view = Gtk.TextView(editable=editable, wrap_mode=Gtk.WrapMode.WORD_CHAR)
        view.set_top_margin(8); view.set_bottom_margin(8); view.set_left_margin(8); view.set_right_margin(8)
        scrolled = Gtk.ScrolledWindow(min_content_height=120, vexpand=True)
        scrolled.set_has_frame(True); scrolled.set_child(view); box.append(scrolled)
        return view

    @staticmethod
    def text(view):
        buffer = view.get_buffer()
        return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)

    def changed(self, *_):
        self.generation += 1
        self.proposed.get_buffer().set_text('')
        self.copy.set_sensitive(False)

    def poll(self):
        if self.closed: return False
        row = self.read_status()
        phase = row.get('phase') if row else 'unavailable'
        self.phase = phase
        names = {'loading': 'Speech model is loading', 'waiting': 'Waiting for memory or cooling headroom',
                 'ready': 'Ready — microphone is off', 'listening': 'Listening — release F5 or stop to finish',
                 'finishing': 'Finishing dictation', 'error': 'Dictation stopped; check the focused field and try again',
                 'stopped': 'Speech service is stopped', 'unavailable': 'Speech service is unavailable'}
        self.state.set_label(names.get(phase, 'Speech service is unavailable'))
        self.record.set_sensitive(phase == 'ready')
        self.mode.set_sensitive(not self.busy)
        self.language.set_sensitive(not self.busy and self.mode.get_selected() == 1)
        self.transform.set_sensitive(not self.busy and phase not in ('listening', 'finishing'))
        return True

    def start_review(self, *_):
        if self.busy or self.phase in ('listening', 'finishing'): return
        source = self.text(self.original)
        generation = self.generation
        mode = 'translate' if self.mode.get_selected() else 'grammar'
        language = LANGUAGES[self.language.get_selected()]
        self.busy = True; self.poll()
        self.proposed.get_buffer().set_text(''); self.copy.set_sensitive(False)
        self.message.set_label('Reviewing locally… Original text is preserved.')
        def worker():
            try: result, error = self.review(source, mode, language), None
            except ReviewUnavailable as exc: result, error = None, str(exc)
            except Exception: result, error = None, 'Local review is unavailable; original text is unchanged'
            def finished():
                if self.closed: return False
                self.busy = False; self.poll()
                if generation != self.generation:
                    self.message.set_label('Original text changed. Review it again when ready.')
                elif error: self.message.set_label(error)
                else:
                    self.proposed.get_buffer().set_text(result); self.copy.set_sensitive(True)
                    self.message.set_label('Check names, numbers, meaning and translation before copying.')
                return False
            GLib.idle_add(finished)
        threading.Thread(target=worker, daemon=True).start()

    def close(self, *_):
        self.closed = True
        self.generation += 1
        if getattr(self, 'timer', None): GLib.source_remove(self.timer)
        # Does not stop someone else's F5/model job. Text is not saved.
        return False


if __name__ == '__main__':
    raise SystemExit(DictationPanel().run())
