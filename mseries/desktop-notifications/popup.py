# SPDX-License-Identifier: GPL-3.0-or-later
"""GTK3 X11 override-redirect popup presentation. No bus ownership on import."""
import math
import cairo
import gi

gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
gi.require_version('GdkX11', '3.0')
from gi.repository import Gdk, GdkX11, Gio, GLib, Gtk, Pango
from model import positions
from workarea import ShellCache, shell_workarea


class Popups:
    def __init__(self):
        self.display = Gdk.Display.get_default()
        if not isinstance(self.display, GdkX11.X11Display):
            raise RuntimeError('Desktop notification placement requires an X11 display')
        self.windows = {}
        self._rendering = False
        self._render_pending = False
        self.store = None
        self.shell_cache = ShellCache(GLib.idle_add, self.render)
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
            .mseries-notification { background: transparent; }
            .mseries-notification .notification-card { background-color: rgb(163, 168, 174);
                color: #20242a; border: 1px solid rgba(32, 36, 42, 0.25);
                border-radius: 10px; }
            .mseries-notification label { color: #20242a; }
            .mseries-notification button { color: #20242a; min-height: 0;
                min-width: 0; padding: 4px 6px; background-image: none;
                background-color: rgba(255, 255, 255, 0.12); box-shadow: none;
                text-shadow: none; border-color: rgba(32, 36, 42, 0.3); }
            .mseries-notification button:hover { background-color: rgba(255,255,255,0.25); }
            .mseries-notification .notification-body { background: none; border: none;
                padding: 0; box-shadow: none; }
            .mseries-notification .traffic { min-height: 12px; min-width: 12px; padding: 0;
                border-radius: 50%; border: 1px solid rgba(0, 0, 0, 0.2); }
            .mseries-notification .traffic label { color: transparent; font-size: 9px;
                font-weight: 800; }
            .mseries-notification .traffic-lights:hover .traffic label { color: rgba(0, 0, 0, 0.6); }
            .mseries-notification .traffic.close { background-color: #ff5f57; }
            .mseries-notification .traffic.close:hover { background-color: #ff453a; }
            .mseries-notification .traffic.minimize { background-color: #febc2e; }
            .mseries-notification .traffic.minimize:hover { background-color: #f5ad0a; }
            .mseries-notification .notification-title { font-weight: bold; }
        ''')
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), css,
                                                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

    def _monitors_changed(self, *_args):
        self.shell_cache.invalidate()
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
        full = monitor.get_geometry()
        geometry = full.x, full.y, full.width, full.height
        top, bottom = self.shell_cache.current(geometry)
        return shell_workarea((rect.x, rect.y, rect.width, rect.height), geometry, top, bottom)

    def render(self):
        if self._rendering:
            self._render_pending = True
            return
        self._rendering = True
        try:
            while True:
                self._render_pending = False
                self._render_once()
                if not self._render_pending:
                    break
        finally:
            self._rendering = False

    def _render_once(self):
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

    @staticmethod
    def _clear_background(_window, context):
        context.set_operator(cairo.OPERATOR_SOURCE)
        context.set_source_rgba(0, 0, 0, 0)
        context.paint()
        context.set_operator(cairo.OPERATOR_OVER)
        return False

    @staticmethod
    def _round_window(window, allocation):
        native = window.get_window()
        if native is None:
            return
        width, height = allocation.width, allocation.height
        radius = min(10, width // 2, height // 2)
        rectangles = []
        for y in range(height):
            dy = max(radius - y - 0.5, y + 0.5 - (height - radius), 0)
            inset = math.ceil(radius - math.sqrt(max(0, radius * radius - dy * dy)))
            rectangles.append(cairo.RectangleInt(inset, y, max(0, width - 2 * inset), 1))
        region = cairo.Region(rectangles)
        # X Shape fallback makes the silhouette rounded without an X compositor.
        native.shape_combine_region(region, 0, 0)
        native.input_shape_combine_region(region, 0, 0)

    def make_window(self, notice, width, height):
        window = Gtk.Window(type=Gtk.WindowType.POPUP)
        window.set_title('M-Series notification')
        visual = window.get_screen().get_rgba_visual()
        if visual:
            window.set_visual(visual)
        window.set_app_paintable(True)
        window.connect('draw', self._clear_background)
        window.connect('size-allocate', self._round_window)
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
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        box.set_border_width(0)
        box.get_style_context().add_class('notification-card')
        window.add(box)
        box.set_margin_start(0)
        box.set_margin_end(0)
        header = Gtk.Box(spacing=8)
        header.set_margin_start(10)
        header.set_margin_end(6)
        header.set_margin_top(4)
        box.pack_start(header, False, False, 0)
        lights = Gtk.Box(spacing=7)
        lights.get_style_context().add_class('traffic-lights')
        lights.set_valign(Gtk.Align.CENTER)
        for kind, glyph, name, reason in (('close', '\u00d7', 'Dismiss notification', 2),
                                          ('minimize', '\u2212', 'Minimize notification', 4)):
            light = Gtk.Button()
            light.add(Gtk.Label(label=glyph))
            light.set_relief(Gtk.ReliefStyle.NONE)
            light.set_can_focus(False)
            light.get_style_context().add_class('traffic')
            light.get_style_context().add_class(kind)
            light.set_tooltip_text(name)
            light.get_accessible().set_name(name)
            light.connect('clicked', lambda _b, r=reason: self.store.close(notice.id, r))
            lights.pack_start(light, False, False, 0)
        header.pack_start(lights, False, False, 0)
        label = Gtk.Label(label=notice.app or 'Notification', xalign=0)
        label.set_ellipsize(Pango.EllipsizeMode.END)
        header.pack_start(label, True, True, 0)
        row = Gtk.Box(spacing=8)
        row.set_margin_start(8)
        row.set_margin_end(8)
        row.set_margin_bottom(4)
        box.pack_start(row, True, True, 0)
        body = Gtk.Button()
        body.get_style_context().add_class('notification-body')
        body.get_accessible().set_name(notice.summary + '\n' + notice.body)
        body.set_relief(Gtk.ReliefStyle.NONE)
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        for value, lines, style in [(notice.summary, 1, 'notification-title'), (notice.body, 1, '')]:
            label = Gtk.Label(label=value, xalign=0, yalign=0)
            label.set_use_markup(False)
            label.set_line_wrap(False)
            label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
            label.set_lines(lines)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_width_chars(1)
            label.set_max_width_chars(max(1, (width - 64) // 9))
            if style:
                label.get_style_context().add_class(style)
            content.pack_start(label, False, False, 0)
        body.add(content)
        body.connect('clicked', lambda *_a: self.store.activate(notice.id, 'default'))
        row.pack_start(body, True, True, 0)
        buttons = Gtk.Box(spacing=4, homogeneous=True)
        buttons.set_valign(Gtk.Align.CENTER)
        for key, title in notice.actions:
            if key == 'default':
                continue
            button = Gtk.Button()
            label = Gtk.Label(label=title)
            label.set_ellipsize(Pango.EllipsizeMode.END)
            label.set_width_chars(1)
            label.set_max_width_chars(7)
            button.set_size_request(60, 30)
            button.set_tooltip_text(title)
            button.add(label)
            button.get_accessible().set_name(title)
            button.connect('clicked', lambda _b, action=key: self.store.activate(notice.id, action))
            buttons.pack_start(button, True, True, 0)
        row.pack_end(buttons, False, False, 0)
        return window
