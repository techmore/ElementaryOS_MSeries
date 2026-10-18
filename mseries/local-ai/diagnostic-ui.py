#!/usr/bin/python3
"""Native, explicitly opened alert inbox; never starts inference on refresh."""
import json
import os
from pathlib import Path
import subprocess
import threading
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib
from alert_store import AlertStore


class Inbox(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.techmore.DiagnosticInbox')
        self.process = None
        self.selected_id = None
        self.selected_version = None
        self.closed = False

    def do_activate(self):
        if self.get_active_window():
            self.get_active_window().present()
            return
        self.window = Gtk.ApplicationWindow(application=self, title='System Troubleshooter')
        self.window.set_default_size(820, 640)
        self.window.connect('close-request', self.close)
        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_top=16, margin_bottom=16, margin_start=16, margin_end=16)
        self.window.set_child(body)
        title = Gtk.Label(label='Kernel and application alerts', xalign=0)
        title.add_css_class('title-2');body.append(title)
        self.status = Gtk.Label(label='Collected locally. Analysis runs only when requested.', xalign=0, wrap=True)
        body.append(self.status)
        self.listing = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.listing.connect('row-selected', self.select)
        scroll = Gtk.ScrolledWindow(min_content_height=150, vexpand=True)
        scroll.set_child(self.listing);body.append(scroll)
        buttons = Gtk.Box(spacing=8)
        for title, callback in [('Refresh', self.refresh), ('Acknowledge', self.acknowledge),
                                ('Analyze selected', self.analyze_alert), ('Check performance', self.performance)]:
            button = Gtk.Button(label=title);button.connect('clicked', callback);buttons.append(button)
        self.cancel = Gtk.Button(label='Cancel analysis', sensitive=False)
        self.cancel.connect('clicked', self.cancel_analysis);buttons.append(self.cancel)
        body.append(buttons)
        self.exclusive = Gtk.CheckButton(label='Allow the idle everyday model to yield for this analysis')
        self.exclusive.set_tooltip_text('Other apps and coding models stay running. The everyday model returns only when quiet admission permits.')
        body.append(self.exclusive)
        self.question = Gtk.Entry(placeholder_text='Optional question about the selected evidence')
        body.append(self.question)
        self.text = Gtk.TextView(editable=False, wrap_mode=Gtk.WrapMode.WORD_CHAR, cursor_visible=False)
        output = Gtk.ScrolledWindow(min_content_height=220, vexpand=True);output.set_child(self.text);body.append(output)
        self.refresh()
        self.window.present()

    def refresh(self, *_args):
        while child := self.listing.get_first_child():
            self.listing.remove(child)
        self.selected_id = None
        self.selected_version = None
        try:
            store = AlertStore(read_only=True)
            rows = store.list_alerts(limit=50)
            for alert in rows:
                row = Gtk.ListBoxRow();row.alert_id = alert['alert_id']
                label = Gtk.Label(label=f"{alert.get('severity', 'notice')} · {alert.get('subsystem', 'system')} · {alert.get('occurrence_count', 1)} occurrence(s) · {alert.get('attention', 'new')}",
                                  xalign=0, margin_top=8, margin_bottom=8, margin_start=8)
                row.set_child(label);self.listing.append(row)
            self.status.set_text(f'{len(rows)} bounded alert(s). Acknowledgement does not mean repaired.')
        except (OSError, ValueError, RuntimeError) as error:
            self.status.set_text('Alert inbox unavailable; no inference started. ' + str(error)[:160])

    def select(self, _listing, row):
        if row is None:return
        try:
            alert = AlertStore(read_only=True).get_alert(row.alert_id)
            self.selected_id, self.selected_version = alert['alert_id'], alert['version']
            self.text.get_buffer().set_text(json.dumps(alert, indent=2, ensure_ascii=False))
        except (OSError, ValueError, RuntimeError):
            self.status.set_text('Alert changed or is unavailable. Refresh to inspect it again.')

    def acknowledge(self, *_args):
        if self.selected_id is None:return
        try:
            AlertStore().acknowledge(self.selected_id, self.selected_version)
            self.refresh()
        except (OSError, ValueError, RuntimeError):
            self.status.set_text('A newer occurrence may have arrived. Refresh before acknowledging it.')

    def analyze_alert(self, *_args):
        if self.selected_id is None:
            self.status.set_text('Select an alert first.');return
        self.start(['--alert', self.selected_id])

    def performance(self, *_args):
        self.start(['--performance'])

    def start(self, args):
        if self.process is not None:
            self.status.set_text('One analysis is already running.');return
        command = [str(Path.home() / '.local/bin/mseries-diagnose'), 'analyze', *args]
        if self.exclusive.get_active():command.append('--exclusive')
        question = self.question.get_text().strip()
        if question:command += ['--question', question[:1000]]
        self.status.set_text('Checking model qualification, quiet admission and evidence…')
        self.cancel.set_sensitive(True)
        self.exclusive.set_sensitive(False)
        self.question.set_sensitive(False)
        # No shell and no model-provided argv. Only this deliberately requested
        # child receives Cancel; unrelated owner jobs are never signalled.
        try:
            self.process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        except OSError:
            self.finished('The diagnostic client is unavailable.', 3);return
        process = self.process
        def wait():
            stdout, _stderr = process.communicate()
            GLib.idle_add(self.finished, stdout[-18000:], process.returncode)
        threading.Thread(target=wait, daemon=True).start()

    def finished(self, output, code):
        self.process = None
        if self.closed:return False
        self.cancel.set_sensitive(False)
        self.exclusive.set_sensitive(True)
        self.question.set_sensitive(True)
        self.status.set_text('Analysis complete; no repair was executed.' if code == 0 else 'Analysis deferred, cancelled or rejected. Evidence remains saved.')
        self.text.get_buffer().set_text(output)
        return False

    def cancel_analysis(self, *_args):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            self.status.set_text('Cancelling this analysis and releasing its model…')

    def close(self, *_args):
        self.closed = True
        self.cancel_analysis()
        return False


if __name__ == '__main__':
    Inbox().run()
