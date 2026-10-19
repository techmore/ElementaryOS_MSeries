"""Orchard application object and entry point."""
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Graphene", "1.0")
gi.require_version("Granite", "7.0")
from gi.repository import Granite, Gtk  # noqa: E402

from .window import APP_ID, Window  # noqa: E402


class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_startup(self):
        Gtk.Application.do_startup(self)
        Gtk.Window.set_default_icon_name(APP_ID)
        # GTK 4 apps on elementary only go dark when they follow Granite's colour-scheme setting
        gs, gtk = Granite.Settings.get_default(), Gtk.Settings.get_default()
        def sync(*_):
            gtk.props.gtk_application_prefer_dark_theme = gs.props.prefers_color_scheme == Granite.SettingsColorScheme.DARK
        gs.connect("notify::prefers-color-scheme", sync)
        sync()

    def do_activate(self):
        (self.props.active_window or Window(self)).present()


def main():
    return App().run()
