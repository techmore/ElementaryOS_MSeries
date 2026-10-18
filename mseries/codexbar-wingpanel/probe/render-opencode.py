#!/usr/bin/env python3
"""Render the real API-key sheet without authentication, network access or stored credentials.

Usage: GTK_THEME=io.elementary.stylesheet.blueberry[:dark] GSK_RENDERER=cairo
       xvfb-run -a /usr/bin/python3 render-opencode.py OUT.png [initial|busy|error]
"""
import importlib.util
from pathlib import Path
import sys
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

spec = importlib.util.spec_from_file_location('login', Path(__file__).resolve().parents[2] / 'codexbar-opencode-login.py')
login = importlib.util.module_from_spec(spec)
spec.loader.exec_module(login)
app = Gtk.Application(application_id='io.github.mseries.OpenCodeStyleProbe')
destination = sys.argv[1]
scenario = sys.argv[2] if len(sys.argv) > 2 else 'initial'
if scenario not in ('initial', 'busy', 'error'):
    raise SystemExit('Expected initial, busy or error')

def activate(application):
    window = login.build_connect_window(application)
    assert not window.save.get_sensitive()
    window.entry.set_text('fixture-key-for-render-only')
    assert window.save.get_sensitive()
    window.entry.set_text('')
    if scenario == 'busy':
        window.entry.set_text('fixture-key-for-render-only')
        window.set_busy(True)
        window.show_status('Checking your key with opencode.ai…', False)
        assert not window.entry.get_sensitive() and not window.here.get_sensitive()
        assert not window.save.get_sensitive() and window.spinner.get_spinning()
    elif scenario == 'error':
        window.entry.set_text('fixture-key-for-render-only')
        window.set_busy(True)
        window.set_busy(False)
        window.show_status("This key wasn't accepted. Check the key and try again.", True)
        assert window.save.get_sensitive() and window.entry.get_sensitive()
        assert window.here.get_sensitive() and not window.spinner.get_spinning()
    window.present()
    window.entry.grab_focus()
    def capture():
        paintable = Gtk.WidgetPaintable.new(window)
        snapshot = Gtk.Snapshot.new()
        paintable.snapshot(snapshot, window.get_width(), window.get_height())
        node = snapshot.to_node()
        texture = window.get_native().get_renderer().render_texture(node, None)
        texture.save_to_png(destination)
        window.close()
        return False
    GLib.timeout_add(800, capture)

app.connect('activate', activate)
app.run([])
