#!/usr/bin/python3
"""Asymmetric synthetic content for screenshot orientation review."""
import os
from pathlib import Path
import gi
gi.require_version("Gtk", "4.0")
from gi.repository import Gtk

app = Gtk.Application(application_id="io.elementary.mseries.ScreenshotFixture")

def activate(application):
    window = Gtk.ApplicationWindow(application=application, title="Screenshot Fixture")
    window.set_default_size(400, 300)
    drawing = Gtk.DrawingArea()
    def draw(_area, context, width, height):
        context.set_source_rgb(0.9, 0.1, 0.1)
        context.rectangle(0, 0, width, height / 2)
        context.fill()
        context.set_source_rgb(0.1, 0.1, 0.9)
        context.rectangle(0, height / 2, width, height / 2)
        context.fill()
        context.set_source_rgb(1, 1, 1)
        context.set_font_size(28)
        context.move_to(20, 50)
        context.show_text("TOP — synthetic capture")
        Path(os.environ["CAPTURE_RECEIPT"], "fixture-ready").touch()
    drawing.set_draw_func(draw)
    window.set_child(drawing)
    window.present()

app.connect("activate", activate)
app.run([])
