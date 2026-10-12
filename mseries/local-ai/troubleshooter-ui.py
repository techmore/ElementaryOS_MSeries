#!/usr/bin/python3
"""Small native GTK4 frontend for the on-device diagnostic command."""
import subprocess
import json
import threading
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk


class Troubleshooter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.techmore.MSeries.Troubleshooter')
        self.connect('activate', self.activate_window)

    def activate_window(self, _app):
        if self.get_active_window():
            self.get_active_window().present()
            return
        window = Gtk.ApplicationWindow(application=self, title='Local Troubleshooter',
                                       default_width=680, default_height=560)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        heading = Gtk.Label(label='What went wrong?', xalign=0)
        heading.add_css_class('title-2')
        box.append(heading)
        box.append(Gtk.Label(label='Gemma 4 analyzes recent warnings on this Mac. No logs are uploaded.',
                             xalign=0, wrap=True))
        self.question = Gtk.Entry(placeholder_text='For example: Why did my desktop freeze?')
        box.append(self.question)
        self.previous = Gtk.CheckButton(label='Use logs from the previous boot')
        box.append(self.previous)
        row = Gtk.Box(spacing=8)
        self.analyze = Gtk.Button(label='Analyze Logs')
        self.analyze.add_css_class('suggested-action')
        self.analyze.connect('clicked', self.run_analysis)
        row.append(self.analyze)
        self.release = Gtk.Button(label='Release Model Memory')
        self.release.connect('clicked', self.stop_model)
        row.append(self.release)
        self.repair = Gtk.Button(label='Restart Panel')
        self.repair.connect('clicked', self.repair_panel)
        row.append(self.repair)
        self.spinner = Gtk.Spinner()
        row.append(self.spinner)
        box.append(row)
        self.status = Gtk.Label(label='Starts the local model when needed. Suggestions are never executed.',
                                xalign=0, wrap=True)
        self.status.add_css_class('dim-label')
        box.append(self.status)
        self.text = Gtk.TextView(editable=False, cursor_visible=False,
                                 wrap_mode=Gtk.WrapMode.WORD_CHAR,
                                 top_margin=12, bottom_margin=12, left_margin=12, right_margin=12)
        scroll = Gtk.ScrolledWindow(vexpand=True, child=self.text)
        scroll.add_css_class('card')
        box.append(scroll)
        window.set_child(box)
        reports = sorted((Path.home() / '.local/state/mseries-troubleshooter').glob('*.md'))
        if reports:
            try:
                self.text.get_buffer().set_text(reports[-1].read_text()[:64000])
                self.status.set_text('Showing the latest saved analysis. Analyze again for current evidence.')
            except OSError:
                pass
        window.present()

    def repair_panel(self, _button):
        self.repair.set_sensitive(False)
        self.status.set_text('Restarting your panel and checking that it stays running…')
        def work():
            try:
                result = subprocess.run(['/usr/bin/python3', str(Path.home() / '.local/libexec/mseries-repair-panel')],
                                        capture_output=True, text=True, timeout=30)
                output = result.stdout + result.stderr
            except (OSError, subprocess.SubprocessError) as error:
                output = str(error)
            GLib.idle_add(self.repair_finished, output)
        threading.Thread(target=work, daemon=True).start()

    def repair_finished(self, output):
        self.repair.set_sensitive(True)
        self.status.set_text(output.strip())
        return False

    def stop_model(self, _button):
        result = subprocess.run(['systemctl', '--user', 'stop', 'mseries-troubleshooter-model.service'],
                                capture_output=True, text=True, timeout=25)
        self.status.set_text('Model memory released.' if result.returncode == 0 else result.stderr)

    def run_analysis(self, _button):
        question = self.question.get_text().strip() or 'Why are there recent desktop failures?'
        args = [str(Path.home() / '.local/bin/mseries-troubleshoot'), '--start', question]
        if self.previous.get_active():
            args.append('--previous-boot')
        self.analyze.set_sensitive(False)
        self.release.set_sensitive(False)
        self.repair.set_sensitive(False)
        self.spinner.start()
        self.status.set_text('Preparing local analysis…')
        self.text.get_buffer().set_text('')
        def work():
            try:
                output_lines = []
                with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                      text=True, bufsize=1) as process:
                    timer = threading.Timer(780, process.kill)
                    timer.start()
                    try:
                        for line in process.stdout:
                            if line.startswith('MSeries-Progress: '):
                                try:
                                    progress = json.loads(line.removeprefix('MSeries-Progress: '))
                                    GLib.idle_add(self.update_stage, progress['detail'])
                                    continue
                                except (ValueError, KeyError, TypeError):
                                    pass
                            output_lines.append(line)
                        success = process.wait() == 0
                    finally:
                        timer.cancel()
                output = ''.join(output_lines)
                if not success and not output.strip():
                    output = 'Local analysis stopped or exceeded the 13 minute time limit.'
            except (OSError, subprocess.SubprocessError) as error:
                output, success = str(error), False
            GLib.idle_add(self.finished, output, success)
        threading.Thread(target=work, daemon=True).start()

    def update_stage(self, detail):
        self.status.set_text(detail)
        return False

    def finished(self, output, success):
        self.text.get_buffer().set_text(output)
        self.spinner.stop()
        self.analyze.set_sensitive(True)
        self.release.set_sensitive(True)
        self.repair.set_sensitive(True)
        self.status.set_text('Analysis saved locally. Verify suggestions before acting.' if success else
                             'Analysis could not finish. Details appear below.')
        return False


Troubleshooter().run(None)
