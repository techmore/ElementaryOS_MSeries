# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK3 X11 override-redirect popup presentation. No bus ownership on import."""
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gdk, GdkX11, Gio, Gtk, Pango
from model import positions


class Popups:
    def __init__(self):
        self.display = Gdk.Display.get_default()
        if not isinstance(self.display, GdkX11.X11Display):
            raise RuntimeError('Desktop notification placement requires an X11 display')
        self.windows = {}
        self.store = None
        source = Gio.SettingsSchemaSource.get_default()
        schema = source.lookup('io.elementary.notifications', True) if source else None
        self.settings = Gio.Settings.new_full(schema, None, None) if schema and schema.has_key('do-not-disturb') else None
        if self.settings:
            self.settings.connect('changed::do-not-disturb', self._dnd_changed)
        self.monitor_handlers = {}
        self.display.connect('monitor-added', self._monitors_changed)
        self.display.connect('monitor-removed', self._monitors_changed)
        self._monitors_changed()
        Gdk.Screen.get_default().connect('monitors-changed', lambda *_a: self.render())
        Gdk.Screen.get_default().connect('size-changed', lambda *_a: self.render())
        css = Gtk.CssProvider()
        css.load_from_data(b'''
            .mseries-notification { background-color: @theme_bg_color;
                color: @theme_fg_color; border: 1px solid alpha(@theme_fg_color, 0.22);
                border-radius: 10px; }
            .mseries-notification .notification-title { font-weight: bold; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _monitors_changed(self, *_args):
        monitors = {self.display.get_monitor(i) for i in range(self.display.get_n_monitors())}
        for monitor in tuple(self.monitor_handlers):
            if monitor not in monitors:
                monitor.disconnect(self.monitor_handlers.pop(monitor))
        for monitor in monitors:
            if monitor not in self.monitor_handlers:
                self.monitor_handlers[monitor] = monitor.connect('notify::workarea', lambda *_a: self.render())
        self.render()

    def muted(self):
        return bool(self.settings and self.settings.get_boolean('do-not-disturb'))

    def _dnd_changed(self, *_args):
        if self.store and self.muted():
            self.store.clear()

    def area(self):
        monitor = self.display.get_primary_monitor() or self.display.get_monitor(0)
        if monitor is None:
            raise RuntimeError('No monitor available')
        rect = monitor.get_workarea()
        return rect.x, rect.y, rect.width, rect.height

    def render(self):
        if self.store is None:
            return
        area = self.area()
        slots = positions(area, 3)
        self.store.limit = len(slots)
        # Avoid reentrant close/render when a monitor shrinks.
        if len(self.store.items) > len(slots):
            self.store.close(next(iter(self.store.items)), 4)
            return
        for nid in tuple(self.windows):
            if nid not in self.store.items:
                self.windows.pop(nid)[1].destroy()
        for notice, (x, y, width, height) in zip(reversed(self.store.items.values()), slots):
            existing = self.windows.get(notice.id)
            if existing and existing[0] != notice:
                existing[1].destroy()
                del self.windows[notice.id]
                existing = None
            window = existing[1] if existing else self.make_window(notice, width, height)
            self.windows[notice.id] = (notice, window)
            window.move(x, y)
            window.show_all()
            window.move(x, y)

    def make_window(self, notice, width, height):
        window = Gtk.Window(type=Gtk.WindowType.POPUP)
        window.set_title('M-Series notification')
        window.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
        window.set_accept_focus(False)
        window.set_focus_on_map(False)
        window.set_skip_taskbar_hint(True)
        window.set_skip_pager_hint(True)
        window.set_resizable(False)
        window.set_default_size(width, height)
        window.set_size_request(width, height)
        window.get_style_context().add_class('mseries-notification')
        window.connect('realize', lambda w: w.get_window().set_override_redirect(True))
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_border_width(12)
        window.add(box)
        header = Gtk.Box(spacing=8)
        box.pack_start(header, False, False, 0)
        label = Gtk.Label(label=notice.app or 'Notification', xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        header.pack_start(label, True, True, 0)
        close = Gtk.Button.new_from_icon_name('window-close-symbolic', Gtk.IconSize.MENU)
        close.set_relief(Gtk.ReliefStyle.NONE)
        close.set_tooltip_text('Dismiss notification')
        close.get_accessible().set_name('Dismiss notification')
        close.connect('clicked', lambda *_a: self.store.close(notice.id, 2))
        header.pack_end(close, False, False, 0)
        body = Gtk.Button()
        body.set_relief(Gtk.ReliefStyle.NONE)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for value, lines, style in [(notice.summary, 1, 'notification-title'), (notice.body, 3, '')]:
            label = Gtk.Label(label=value, xalign=0, yalign=0)
            label.set_use_markup(False)
            label.set_line_wrap(True)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_lines(lines)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(max(1, (width - 64) // 9))
            if style:
                label.get_style_context().add_class(style)
            content.pack_start(label, False, False, 0)
        body.add(content)
        body.connect('clicked', lambda *_a: self.store.activate(notice.id, 'default'))
        box.pack_start(body, True, True, 0)
        buttons = Gtk.Box(spacing=8, homogeneous=True)
        for key, title in notice.actions:
            if key == 'default':
                continue
            button = Gtk.Button()
            label = Gtk.Label(label=title)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_max_width_chars(12)
            button.add(label)
            button.get_accessible().set_name(title)
            button.connect('clicked', lambda _b, action=key: self.store.activate(notice.id, action))
            buttons.pack_start(button, True, True, 0)
        box.pack_end(buttons, False, False, 0)
        return window
