#!/usr/bin/python3
"""English dictation and optional English grammar suggestions. Text stays ephemeral."""
import threading
import time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk
from dictation_review import ReviewUnavailable, review
from dictation_status import read_status
from dictation_live import LiveEnglishReview


class DictationPanel(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.techmore.Dictation', flags=Gio.ApplicationFlags.DEFAULT_FLAGS)
        self.window = None
        self.busy = False
        self.closed = False
        self.generation = 0
        self.review = review
        self.read_status = read_status
        self.live = LiveEnglishReview()
        self.clock = time.monotonic
        self.preview_source = ''

    def do_activate(self):
        if self.window:
            self.window.present(); return
        self.window = Gtk.ApplicationWindow(application=self, title='Dictation')
        self.window.set_default_size(660, 560)
        self.window.connect('close-request', self.close)
        self.window.set_titlebar(Gtk.HeaderBar())
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for side in ('top', 'bottom', 'start', 'end'): getattr(box, 'set_margin_' + side)(18)
        self.window.set_child(box)
        title = Gtk.Label(label='English dictation', xalign=0)
        title.add_css_class('title-2'); box.append(title)
        box.append(Gtk.Label(label='Focus the original transcript and use F5. With toggle mode, press again to finish; with hold mode, release. English words appear as you speak.', wrap=True, xalign=0))
        self.record = Gtk.Button(label='Focus transcript for F5')
        self.record.set_focus_on_click(False)
        self.record.connect('clicked', lambda *_: self.original.grab_focus()); box.append(self.record)
        self.state = Gtk.Label(label='', xalign=0, wrap=True); box.append(self.state)
        self.original = self.editor(box, 'Original English transcript', editable=True)
        self.original.get_buffer().connect('changed', self.changed)
        self.live_toggle = Gtk.CheckButton(label='Improve English grammar after dictation')
        self.live_toggle.set_active(True)
        self.live_toggle.connect('toggled', self.changed); box.append(self.live_toggle)
        self.preview_toggle = Gtk.CheckButton(label='Also preview English cleanup while speaking')
        self.preview_toggle.set_tooltip_text('Optional local model work. Suggestions may change; raw English words remain visible. Waits for memory and cooling headroom.')
        self.preview_toggle.connect('toggled', self.changed); box.append(self.preview_toggle)
        self.transform = Gtk.Button(label='Review English grammar')
        self.transform.connect('clicked', self.start_review); box.append(self.transform)
        self.proposed = self.editor(box, 'Suggested English — check meaning before copying', editable=False)
        self.copy = Gtk.Button(label='Copy suggested English')
        self.copy.set_sensitive(False)
        self.copy.connect('clicked', lambda *_: self.window.get_clipboard().set(self.text(self.proposed))); box.append(self.copy)
        self.message = Gtk.Label(label='Original text is never replaced automatically.', xalign=0, wrap=True); box.append(self.message)
        self.poll(); self.timer = GLib.timeout_add(500, self.poll); self.window.present()

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

    def changed(self, widget, *_):
        self.generation += 1
        self.copy.set_sensitive(False)
        self.edit_phase = getattr(self, 'phase', 'unavailable')
        self.force_clear = getattr(self, 'force_clear', False) or widget != self.original.get_buffer()
        if not getattr(self, 'edit_id', None):
            self.edit_id = GLib.idle_add(lambda: self.flush_changed(True))

    def flush_changed(self, from_idle=False):
        if not getattr(self, 'edit_id', None): return False
        if not from_idle: GLib.source_remove(self.edit_id)
        self.edit_id = None
        source = self.text(self.original)
        preserve = (not self.force_clear and self.live_toggle.get_active() and self.preview_source
                    and source.startswith(self.preview_source))
        self.force_clear = False
        if not preserve:
            self.proposed.get_buffer().set_text(''); self.preview_source = ''
        # Gtk.set_text may emit deletion then insertion. Observe the coherent
        # buffer once, retaining the capture phase at the edit for a short final.
        self.live.observe(source,
            self.live_toggle.get_active() and self.edit_phase in ('ready','loading','listening','finishing'),
            self.preview_toggle.get_active(), self.edit_phase != 'ready',
            self.window.get_focus() == self.original, self.clock())
        return False

    def observe_live(self):
        self.flush_changed()
        self.live.observe(self.text(self.original),
            self.live_toggle.get_active() and self.phase in ('ready','loading','listening','finishing'),
            self.preview_toggle.get_active(), self.phase != 'ready',
            self.window.get_focus() == self.original, self.clock())

    def poll(self):
        if self.closed: return False
        row = self.read_status(); self.phase = row.get('phase') if row else 'unavailable'
        names = {'loading':'Speech model is loading', 'waiting':'Waiting for memory or cooling headroom',
            'ready':'Ready — microphone is off', 'listening':'Listening — use F5 to finish',
            'finishing':'Finishing dictation', 'error':'Dictation stopped; check the focused field and try again',
            'cancelled':'Dictation cancelled — original text is preserved', 'stopped':'Speech service is stopped',
            'unavailable':'Speech service is unavailable'}
        self.state.set_label(names.get(self.phase, names['unavailable']))
        self.record.set_sensitive(self.phase not in ('loading','listening','finishing'))
        self.transform.set_sensitive(not self.busy and self.phase not in ('loading','listening','finishing'))
        self.observe_live()
        if not self.busy:
            request = self.live.take(self.clock())
            if request: self.launch_review(request.source, request=request)
            elif self.live.finalized and self.preview_source == self.text(self.original): self.copy.set_sensitive(True)
        return True

    def start_review(self, *_):
        if self.busy or self.phase in ('loading','listening','finishing'): return
        self.live.session = False
        self.launch_review(self.text(self.original))

    def launch_review(self, source, request=None):
        generation = self.generation; self.busy = True; self.copy.set_sensitive(False)
        self.transform.set_sensitive(False)
        self.message.set_label('Reviewing English locally… Original text is preserved.')
        def worker():
            try: value, error = self.review(source, 'grammar', 'English'), None
            except ReviewUnavailable as exc: value, error = None, str(exc)
            except Exception: value, error = None, 'Local English review is unavailable; original text is preserved.'
            def finished():
                if self.closed: return False
                self.busy = False; self.observe_live()
                if request:
                    output = self.live.finish(request, value, error)
                    if output: self.show_proposal(source, *output)
                    elif error: self.message.set_label(error)
                elif generation != self.generation: self.message.set_label('Original text changed. Review it again when ready.')
                elif error: self.message.set_label(error)
                else: self.show_proposal(source, value, True)
                self.poll(); return False
            GLib.idle_add(finished)
        threading.Thread(target=worker, daemon=True).start()

    def show_proposal(self, source, text, final):
        self.proposed.get_buffer().set_text(text); self.preview_source = source
        self.copy.set_sensitive(final)
        self.message.set_label('Check names, numbers and meaning before copying.' if final else 'English cleanup preview — wording may change as you speak.')

    def close(self, *_):
        self.closed = True; self.generation += 1
        if getattr(self, 'timer', None): GLib.source_remove(self.timer)
        if getattr(self, 'edit_id', None): GLib.source_remove(self.edit_id); self.edit_id = None
        return False


if __name__ == '__main__': raise SystemExit(DictationPanel().run())
