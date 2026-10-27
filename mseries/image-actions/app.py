#!/usr/bin/python3
"""Native Files conversion action: explicit local copies, progress and results."""
import argparse
import json
import sys
import threading
from conversion import ConversionError, PixbufEncoder, convert


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["jpeg", "jpeg2000"], default="jpeg")
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("files", nargs="+")
    args = parser.parse_args()
    if args.headless and len(args.files) > 64:
        parser.error("Select at most 64 images at a time.")
    if args.headless:
        encoder = PixbufEncoder()
        failed = False
        for source in args.files:
            try:
                print(json.dumps({"source": source, "output": str(convert(source, args.format, encoder))}))
            except ConversionError as error:
                print(json.dumps({"source": source, "error": str(error)}))
                failed = True
        return int(failed)
    return run_gui(args)


def run_gui(args, on_ready=None):
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Granite", "7.0")
    from gi.repository import Gtk, Granite, GLib, Gio, Pango

    class Application(Gtk.Application):
        def __init__(self):
            super().__init__(application_id="org.techmore.mseries.ImageActions", flags=Gio.ApplicationFlags.NON_UNIQUE)
            self.cancelled = threading.Event()
            self.busy = True
            self.connect("activate", self.activate)

        def activate(self, *_):
            if hasattr(self, "window"):
                self.window.present()
                return
            preferences = Granite.Settings.get_default()
            def scheme(*_):
                Gtk.Settings.get_default().set_property("gtk-application-prefer-dark-theme",
                    preferences.get_prefers_color_scheme() == Granite.SettingsColorScheme.DARK)
            preferences.connect("notify::prefers-color-scheme", scheme)
            scheme()
            title = "Convert to JPEG" if args.format == "jpeg" else "Convert to JPEG 2000"
            self.window = Gtk.ApplicationWindow(application=self, title=title, default_width=560, default_height=360)
            self.window.set_titlebar(Gtk.HeaderBar())
            self.window.connect("close-request", self.close_request)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
            for edge in ("top", "bottom", "start", "end"):
                getattr(box, "set_margin_" + edge)(18)
            self.window.set_child(box)
            heading = Gtk.Label(label=title, xalign=0)
            heading.add_css_class("title-2")
            box.append(heading)
            box.append(Gtk.Label(label="A new copy is saved beside each image. Originals stay unchanged. Transparent areas become white.",
                                 wrap=True, xalign=0))
            self.status = Gtk.Label(label="Preparing conversion…", wrap=True, xalign=0)
            box.append(self.status)
            self.progress = Gtk.ProgressBar(show_text=True)
            self.progress.set_text(f"0 of {len(args.files)}")
            box.append(self.progress)
            self.results = Gtk.Label(label="", wrap=True, selectable=True, xalign=0, yalign=0)
            self.results.set_wrap_mode(Pango.WrapMode.WORD_CHAR)
            scroll = Gtk.ScrolledWindow(vexpand=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
            scroll.set_child(self.results)
            box.append(scroll)
            self.button = Gtk.Button(label="Cancel", halign=Gtk.Align.END)
            self.button.connect("clicked", self.button_clicked)
            box.append(self.button)
            self.window.present()
            if on_ready is not None:
                on_ready(self)
            threading.Thread(target=self.work, daemon=True).start()

        def button_clicked(self, *_):
            if self.busy:
                self.cancelled.set()
                self.status.set_text("Cancelling after the current encoder operation…")
                self.button.set_sensitive(False)
            else:
                self.window.close()

        def close_request(self, *_):
            if self.busy:
                self.button_clicked()
                return True
            return False

        def update(self, completed, lines):
            self.progress.set_fraction(completed / len(args.files))
            self.progress.set_text(f"{completed} of {len(args.files)}")
            self.results.set_text("\n\n".join(lines))
            return False

        def work(self):
            lines, successes, failures = [], 0, 0
            try:
                if len(args.files) > 64:
                    raise ConversionError("Select at most 64 images at a time.")
                encoder = PixbufEncoder()
                for number, source in enumerate(args.files, 1):
                    if self.cancelled.is_set():
                        break
                    GLib.idle_add(self.status.set_text, f"Converting {number} of {len(args.files)}…")
                    try:
                        output = convert(source, args.format, encoder, self.cancelled.is_set)
                        lines.append(f"Saved {output.name}")
                        successes += 1
                    except ConversionError as error:
                        lines.append(f"{source}\n{error}")
                        failures += 1
                    GLib.idle_add(self.update, number, list(lines))
            except Exception as error:
                lines.append(f"Conversion unavailable: {error}")
                failures = len(args.files) - successes
            GLib.idle_add(self.finish, successes, failures, lines)

        def finish(self, successes, failures, lines):
            self.busy = False
            self.results.set_text("\n\n".join(lines))
            summary = ("1 copy saved" if successes == 1 else f"{successes} copies saved") + f" · {failures} failed"
            if self.cancelled.is_set():
                summary += " · Cancelled"
            self.status.set_text(summary)
            self.button.set_label("Close")
            self.button.set_sensitive(True)
            notification = Gio.Notification.new("Image conversion finished")
            notification.set_body(summary)
            self.send_notification("conversion", notification)
            return False

    return Application().run([sys.argv[0]])


if __name__ == "__main__":
    raise SystemExit(main())
