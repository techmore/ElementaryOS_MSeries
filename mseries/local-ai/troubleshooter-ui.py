#!/usr/bin/python3
"""Small native GTK4 frontend for the on-device diagnostic command."""
import subprocess
import json
import sys
import threading
import os
import signal
from pathlib import Path
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gio, GLib, Gtk


class Troubleshooter(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.techmore.MSeries.Troubleshooter',
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.connect('command-line', self.command_line)
        self.connect('activate', self.activate_window)
        self._verification_generation = 0
        self._verification_cancel = None
        self._verification_busy = False

    def command_line(self, _app, command_line):
        self.activate()
        if '--performance' in command_line.get_arguments():
            self.performance.set_active(True)
        return 0

    def activate_window(self, _app):
        if self.get_active_window():
            self.get_active_window().present()
            return
        self._verification_generation += 1
        window = Gtk.ApplicationWindow(application=self, title='Local Troubleshooter',
                                       default_width=680, default_height=560)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12,
                      margin_top=18, margin_bottom=18, margin_start=18, margin_end=18)
        heading = Gtk.Label(label='What went wrong?', xalign=0)
        heading.add_css_class('title-2')
        box.append(heading)
        box.append(Gtk.Label(label='The shared local Qwen model analyzes recent warnings on this Mac. No logs are uploaded.',
                             xalign=0, wrap=True))
        self.question = Gtk.Entry(placeholder_text='For example: Why did my desktop freeze?')
        self.question.update_property([Gtk.AccessibleProperty.LABEL], ['Describe the problem'])
        box.append(self.question)
        self.previous = Gtk.CheckButton(label='Use logs from the previous boot')
        box.append(self.previous)
        self.performance = Gtk.CheckButton(label='Check native desktop performance')
        box.append(self.performance)
        self.free_after = Gtk.CheckButton(label='Release model memory after analysis', active=True)
        box.append(self.free_after)
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
        self.checklist = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        box.append(self.checklist)
        self.verification_status = Gtk.Label(xalign=0, wrap=True)
        self.verification_status.add_css_class('dim-label')
        box.append(self.verification_status)
        self.verify_button = Gtk.Button(label='Run checks now', halign=Gtk.Align.START)
        self.verify_button.connect('clicked', self.run_checks)
        box.append(self.verify_button)
        window.connect('close-request', self.cancel_verification)
        self.refresh_checklist()
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

    def cancel_verification(self, _window=None):
        self._verification_generation += 1
        if self._verification_cancel is not None:
            self._verification_cancel.set()
        self._verification_busy = False
        return False

    @staticmethod
    def verification_command(args, timeout, cancelled):
        """Run only verification commands off the GTK thread; reap on close/timeout."""
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, start_new_session=True) as process:
            import time
            deadline = time.monotonic() + timeout
            try:
                while not cancelled.is_set():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise subprocess.TimeoutExpired(args, timeout)
                    try:
                        output, _error = process.communicate(timeout=min(0.1, remaining))
                        if process.returncode != 0:
                            raise RuntimeError('Verification command failed')
                        return output
                    except subprocess.TimeoutExpired:
                        if time.monotonic() >= deadline:
                            raise
                raise RuntimeError('Verification cancelled')
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate(timeout=2)

    def start_verification(self, arguments, timeout, message):
        if self._verification_busy:
            return
        self._verification_generation += 1
        generation = self._verification_generation
        cancelled = threading.Event()
        self._verification_cancel = cancelled
        self._verification_busy = True
        self.verify_button.set_sensitive(False)
        self.checklist.set_sensitive(False)
        self.verification_status.set_text(message)
        tool = str(Path.home() / '.local/bin/mseries-verify')

        def work():
            try:
                if arguments is not None:
                    self.verification_command([tool, *arguments], timeout, cancelled)
                output = self.verification_command([tool, 'status', '--json'], 10, cancelled)
                items = json.loads(output)['items']
                if not isinstance(items, list) or any(
                    not isinstance(item, dict) or
                    not isinstance(item.get('id'), str) or
                    not isinstance(item.get('title'), str) or
                    item.get('state') not in ('ask', 'failed', 'waiting', 'passed')
                    for item in items
                ):
                    raise ValueError('Invalid verification status')
                error = None
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.SubprocessError):
                items, error = None, 'Checks are unavailable. Try again.'
            GLib.idle_add(self.verification_finished, generation, items, error)
        threading.Thread(target=work, daemon=True).start()

    def verification_finished(self, generation, items, error):
        if generation != self._verification_generation:
            return False
        self._verification_busy = False
        self._verification_cancel = None
        self.verify_button.set_sensitive(True)
        self.checklist.set_sensitive(True)
        if error:
            self.verification_status.set_text(error)
            return False
        child = self.checklist.get_first_child()
        while child is not None:
            following = child.get_next_sibling()
            self.checklist.remove(child)
            child = following
        pending = [item for item in items if item['state'] in ('ask', 'failed', 'waiting')]
        self.verification_status.set_text(
            f'Checks still open ({len(pending)})' if pending else 'No checks need attention.')
        icons = {'ask': '?', 'failed': '\u2717', 'waiting': '\u2026'}
        for item in pending:
            row = Gtk.Box(spacing=8)
            row.append(Gtk.Label(label=icons[item['state']]))
            label = Gtk.Label(label=item['title'], xalign=0, hexpand=True, wrap=True,
                              tooltip_text=item.get('detail') if isinstance(item.get('detail'), str) else '')
            if item['state'] != 'ask':
                label.add_css_class('dim-label')
            row.append(label)
            if item['state'] == 'ask':
                for text, answer in (('Looks good', 'yes'), ('Problem', 'no')):
                    button = Gtk.Button(label=text)
                    button.connect('clicked', self.answer_check, item['id'], answer)
                    row.append(button)
            self.checklist.append(row)
        return False

    def refresh_checklist(self):
        self.start_verification(None, 10, 'Loading checks…')

    def answer_check(self, _button, check_id, answer):
        self.start_verification(['confirm', check_id, answer], 10, 'Saving your answer…')

    def run_checks(self, _button):
        self.start_verification(['run', '--quiet'], 120, 'Running checks…')

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
        self.release.set_sensitive(False)
        self.analyze.set_sensitive(False)
        self.status.set_text('Releasing model memory…')
        def work():
            try:
                # Share the same lock as CLI/watcher analyses before unloading.
                import fcntl
                import os
                directory = Path.home() / '.local/state/mseries-troubleshooter'
                directory.mkdir(parents=True, exist_ok=True, mode=0o700)
                with open(directory / 'analysis.lock', 'a',
                          opener=lambda path, flags: os.open(path, flags, 0o600)) as lock:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    result = subprocess.run(['systemctl', '--user', 'stop', 'mseries-ai-everyday.service'],
                                            capture_output=True, text=True, timeout=25)
                    message = 'Model memory released.' if result.returncode == 0 else result.stderr
            except BlockingIOError:
                message = 'Another analysis is running. Wait until it finishes before releasing memory.'
            except (OSError, subprocess.SubprocessError) as error:
                message = str(error)
            GLib.idle_add(self.memory_released, message)
        threading.Thread(target=work, daemon=True).start()

    def memory_released(self, message):
        self.release.set_sensitive(True)
        self.analyze.set_sensitive(True)
        self.status.set_text(message)
        return False

    def run_analysis(self, _button):
        question = self.question.get_text().strip() or (
            'Find native desktop performance bottlenecks and recommend measured, reversible improvements.'
            if self.performance.get_active() else 'Why are there recent desktop failures?')
        args = [str(Path.home() / '.local/bin/mseries-troubleshoot'), '--start', question]
        if self.performance.get_active():
            args.append('--performance')
        if self.free_after.get_active():
            args.append('--release-model')
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


if __name__ == '__main__':
    Troubleshooter().run(sys.argv)
