#!/usr/bin/env python3
"""Native elementary desktop UI; secrets travel only over private child pipes."""
import json
import os
from pathlib import Path
import subprocess
import threading
from datetime import datetime

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Granite', '7.0')
from gi.repository import Gtk, Granite, GLib

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get('XDG_DATA_HOME', Path.home() / '.local/share'))
SOURCE = DATA / 'mseries/icloud-passwords/source'


class Passwords(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='org.techmore.mseries.ApplePasswords')
        self.proc = None
        self.items = []
        self.recovering = False
        self.dialog = None
        self.error_seen = False
        self.credentials = {}
        self.connect('activate', self.activate)

    def activate(self, *_):
        if hasattr(self, 'window'):
            self.window.present()
            return
        prefs = Granite.Settings.get_default()
        settings = Gtk.Settings.get_default()
        def scheme(*_):
            settings.set_property('gtk-application-prefer-dark-theme',
                                  prefs.get_prefers_color_scheme() == Granite.SettingsColorScheme.DARK)
        prefs.connect('notify::prefers-color-scheme', scheme)
        scheme()
        self.window = Gtk.ApplicationWindow(application=self, title='Apple Passwords')
        self.window.set_default_size(900, 640)
        self.window.connect('close-request', self.close)
        header = Gtk.HeaderBar()
        header.set_title_widget(Gtk.Label(label='Apple Passwords'))
        badge = Gtk.Label(label='Experimental')
        badge.add_css_class('warning')
        header.pack_start(badge)
        self.sync = Gtk.Button(label='Sync Now', sensitive=False)
        self.sync.connect('clicked', lambda *_: self.start('sync'))
        header.pack_end(self.sync)
        self.window.set_titlebar(header)
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(root, 'set_margin_' + edge)(20)
        self.window.set_child(root)
        self.status = Gtk.Label(label='Read your iCloud passwords on this Mac.', xalign=0, wrap=True)
        root.append(self.status)
        self.stack = Gtk.Stack(vexpand=True)
        root.append(self.stack)
        self.build_login()
        self.build_vault()
        footer = Gtk.Box(spacing=10)
        self.spinner = Gtk.Spinner()
        footer.append(self.spinner)
        self.cancel = Gtk.Button(label='Cancel', visible=False)
        self.cancel.connect('clicked', self.cancel_work)
        footer.append(self.cancel)
        self.logout = Gtk.Button(label='Sign Out', visible=False)
        self.logout.connect('clicked', lambda *_: self.start('logout'))
        footer.append(self.logout)
        self.unlock = Gtk.Button(label='Sign In Again', visible=False)
        self.unlock.connect('clicked', lambda *_: self.stack.set_visible_child_name('login'))
        footer.append(self.unlock)
        self.browser = Gtk.Button(label='Brave Setup')
        self.browser.connect('clicked', self.brave_help)
        footer.append(self.browser)
        root.append(footer)
        self.window.present()
        self.start('load')

    def build_login(self):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16,
                      halign=Gtk.Align.CENTER, valign=Gtk.Align.CENTER)
        box.set_size_request(460, -1)
        icon = Gtk.Image.new_from_icon_name('dialog-password')
        icon.set_pixel_size(64)
        box.append(icon)
        title = Gtk.Label(label='Your Apple passwords, on elementary OS')
        title.add_css_class('title-2')
        box.append(title)
        note = Gtk.Label(label='Sign in to download an encrypted, read-only snapshot.\n'
                         'This unofficial client is experimental.', wrap=True)
        box.append(note)
        self.email = Gtk.Entry(placeholder_text='Apple Account email', input_purpose=Gtk.InputPurpose.EMAIL)
        self.email.set_max_length(320)
        self.password = Gtk.PasswordEntry(placeholder_text='Apple Account password', show_peek_icon=True)
        self.password.connect('activate', self.login)
        box.append(self.email)
        box.append(self.password)
        self.remember = Gtk.CheckButton(label='Remember password in encrypted storage for background refresh')
        self.remember.set_tooltip_text('Uses your login keyring. Without this, some token renewals and Hide My Email need sign-in again.')
        box.append(self.remember)
        self.signin = Gtk.Button(label='Sign In with Apple')
        self.signin.add_css_class('suggested-action')
        self.signin.connect('clicked', self.login)
        box.append(self.signin)
        warning = Gtk.Label(label='Keep a trusted Apple device nearby for verification.\n'
                            'Recovery requires its known passcode; never guess.', wrap=True)
        warning.add_css_class('dim-label')
        box.append(warning)
        self.stack.add_named(box, 'login')

    def build_vault(self):
        pane = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL, vexpand=True)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.search = Gtk.SearchEntry(placeholder_text='Search passwords')
        self.search.connect('search-changed', lambda *_: self.populate())
        left.append(self.search)
        self.list = Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
        self.list.connect('row-selected', self.select)
        scroll = Gtk.ScrolledWindow(vexpand=True, min_content_width=280)
        scroll.set_child(self.list)
        left.append(scroll)
        pane.set_start_child(left)
        pane.set_resize_start_child(True)
        pane.set_position(330)
        detail = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        detail.set_margin_start(24)
        self.site = Gtk.Label(label='Choose a saved login', xalign=0, wrap=True)
        self.site.add_css_class('title-2')
        self.username = Gtk.Label(xalign=0, selectable=True, wrap=True)
        self.saved_password = Gtk.PasswordEntry(show_peek_icon=True, editable=False)
        self.saved_password.set_visible(False)
        detail.append(self.site)
        detail.append(self.username)
        detail.append(self.saved_password)
        self.snapshot_label = Gtk.Label(xalign=0, wrap=True)
        self.snapshot_label.add_css_class('dim-label')
        detail.append(self.snapshot_label)
        detail.append(Gtk.Label(label='Read-only snapshot. Use the Brave extension for autofill and verification codes.',
                                xalign=0, wrap=True))
        pane.set_end_child(detail)
        self.stack.add_named(pane, 'vault')

    def login(self, *_):
        if self.proc:
            return
        email, password = self.email.get_text().strip(), self.password.get_text()
        if not email or not password:
            self.status.set_text('Enter your Apple Account email and password.')
            return
        self.credentials = {'email': email, 'password': password}
        self.password.set_text('')
        self.start('login')

    def start(self, action):
        if self.proc:
            return
        self.action = action
        self.error_seen = False
        self.recovering = False
        if action in ('login', 'sync'):
            result = subprocess.run(['systemctl', '--user', 'start', 'mseries-icloud-anisette.service'],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if result.returncode:
                self.status.set_text('The local authentication helper could not start.')
                self.credentials.clear()
                return
        args = [str(SOURCE / '.venv/bin/python'), str(HERE / 'worker.py'), action]
        if action == 'login' and self.remember.get_active():
            args.append('--remember-password')
        env = dict(os.environ, ICP_ANISETTE_URL='http://127.0.0.1:6969',
                   REQUESTS_CA_BUNDLE=str(DATA / 'mseries/icloud-passwords/ca-bundle.pem'))
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.DEVNULL, text=True, bufsize=1, env=env)
        except OSError:
            self.status.set_text('The client is unavailable. Run the experimental installer first.')
            self.credentials.clear()
            return
        proc = self.proc
        self.busy(True)
        self.status.set_text('Opening your encrypted snapshot…' if action == 'load' else 'Connecting to Apple…')
        def reader():
            try:
                for line in proc.stdout:
                    try:
                        event = json.loads(line)
                    except (ValueError, TypeError):
                        continue  # never print unrecognized output
                    GLib.idle_add(self.event, proc, event)
            finally:
                proc.wait()
                GLib.idle_add(self.finished, proc)
        threading.Thread(target=reader, daemon=True).start()

    def busy(self, value):
        self.signin.set_sensitive(not value)
        self.sync.set_sensitive(not value and getattr(self, 'joined', False))
        self.logout.set_sensitive(not value)
        self.unlock.set_sensitive(not value)
        self.cancel.set_visible(value)
        self.cancel.set_sensitive(not self.recovering)
        self.spinner.set_spinning(value)

    def reply(self, value=None, cancel=False):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.stdin.write(json.dumps({'value': value, 'cancel': cancel}) + '\n')
                self.proc.stdin.flush()
            except (BrokenPipeError, OSError):
                pass

    def event(self, proc, event):
        if proc is not self.proc:
            return False
        kind = event.get('type')
        if kind == 'prompt':
            field = event.get('kind')
            if field in self.credentials:
                self.reply(self.credentials.pop(field))
            else:
                self.show_prompt(event)
        elif kind in ('error', 'warning'):
            self.error_seen = True
            self.status.set_text(event['text'])
        elif kind == 'progress' and not self.error_seen:
            self.status.set_text(event['text'])
        elif kind == 'recovery':
            self.recovering = True
            self.cancel.set_sensitive(False)
            self.status.set_text('Recovering keychain access. Keep this window open; this attempt cannot be undone.')
        elif kind == 'vault':
            self.items = event['credentials']
            self.joined = event['joined']
            self.signed_in = event['signed_in']
            self.logout.set_visible(self.signed_in)
            self.unlock.set_visible(self.signed_in)
            self.stack.set_visible_child_name('vault' if self.joined else 'login')
            stamp = event.get('updated')
            self.snapshot_label.set_text('Last synced ' + datetime.fromtimestamp(stamp).strftime('%b %d, %H:%M') if stamp else 'No password snapshot yet')
            self.populate()
            if not self.error_seen:
                self.status.set_text(f'{len(self.items)} saved passwords' if self.joined else
                                     'Signed in. Complete keychain setup to download passwords.' if self.signed_in else
                                     'Sign in to read your iCloud passwords.')
        return False

    def show_prompt(self, event):
        dialog = Gtk.Dialog(title=event['label'], transient_for=self.window, modal=True)
        self.dialog = dialog
        dialog.set_default_size(460, -1)
        dialog.add_button('Cancel', Gtk.ResponseType.CANCEL)
        accept = dialog.add_button('Continue', Gtk.ResponseType.OK)
        body = dialog.get_content_area()
        body.set_spacing(16)
        for edge in ('top', 'bottom', 'start', 'end'):
            getattr(body, 'set_margin_' + edge)(20)
        kind = event['kind']
        if kind == 'confirm':
            body.append(Gtk.Label(label='A wrong device passcode uses one of a limited number of recovery attempts. '
                                  'Too many wrong attempts can permanently destroy the recovery record. '
                                  'Continue only if you know the passcode for the device you selected.', wrap=True, max_width_chars=52))
            control = Gtk.CheckButton(label='I know this device’s passcode and allow one attempt')
            accept.set_sensitive(False)
            control.connect('toggled', lambda c: accept.set_sensitive(c.get_active()))
        elif kind == 'device':
            control = Gtk.DropDown.new_from_strings(event.get('choices', []))
            body.append(Gtk.Label(label='Choose the device whose unlock passcode you know.', wrap=True))
        else:
            body.append(Gtk.Label(label=event.get('description', 'Tap Allow on your Apple device, then enter the six-digit code. This window will wait.') if kind == 'code' else
                                  'Enter the unlock passcode for the device you selected.', wrap=True))
            control = Gtk.PasswordEntry(show_peek_icon=kind != 'code')
            control.connect('activate', lambda *_: dialog.response(Gtk.ResponseType.OK))
        body.append(control)
        def respond(_, response):
            if response == Gtk.ResponseType.OK:
                value = 'yes' if kind == 'confirm' else str(control.get_selected()) if kind == 'device' else control.get_text()
                if kind not in ('confirm', 'device') and not value:
                    return
                if kind == 'passcode':
                    self.recovering = True
                    self.cancel.set_sensitive(False)
                    self.status.set_text('Recovering keychain access. Keep this window open until the attempt finishes.')
                self.reply(value)
            else:
                self.reply(cancel=True)
            if kind not in ('confirm', 'device'):
                control.set_text('')
            dialog.destroy()
            self.dialog = None
        dialog.connect('response', respond)
        dialog.present()
        control.grab_focus()

    def finished(self, proc):
        if proc is not self.proc:
            return False
        self.proc = None
        self.credentials.clear()
        self.recovering = False
        if self.dialog:
            self.dialog.destroy()
            self.dialog = None
        self.busy(False)
        if proc.returncode and not self.error_seen:
            self.status.set_text('Operation cancelled.' if proc.returncode in (-15, 130) else 'The client stopped before completing this operation.')
        return False

    def cancel_work(self, *_):
        self.credentials.clear()
        if self.proc and not self.recovering:
            self.proc.terminate()
            self.credentials.clear()

    def populate(self):
        self.saved_password.get_delegate().set_visibility(False)
        self.saved_password.set_text('')
        self.saved_password.set_visible(False)
        self.site.set_text('Choose a saved login')
        self.username.set_text('')
        while child := self.list.get_first_child():
            self.list.remove(child)
        query = self.search.get_text().casefold()
        for item in self.items:
            if query and query not in ' '.join((item['domain'], item['username'], item['title'])).casefold():
                continue
            row = Gtk.ListBoxRow()
            row.item = item
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            for edge in ('top', 'bottom', 'start', 'end'):
                getattr(box, 'set_margin_' + edge)(10)
            box.append(Gtk.Label(label=item['title'] or item['domain'], xalign=0, ellipsize=3))
            name = Gtk.Label(label=item['username'], xalign=0, ellipsize=3)
            name.add_css_class('dim-label')
            box.append(name)
            row.set_child(box)
            self.list.append(row)

    def select(self, _, row):
        self.saved_password.get_delegate().set_visibility(False)
        self.saved_password.set_text('')
        self.saved_password.set_visible(False)
        if row:
            self.site.set_text(row.item['domain'] or row.item['title'])
            self.username.set_text(row.item['username'])
            self.saved_password.set_text(row.item['password'])
            self.saved_password.set_visible(True)

    def brave_help(self, *_):
        dialog = Gtk.MessageDialog(transient_for=self.window, modal=True,
                                   message_type=Gtk.MessageType.INFO, buttons=Gtk.ButtonsType.CLOSE,
                                   text='Enable Apple Passwords in Brave',
                                   secondary_text='Open brave://extensions, enable Developer mode, then Load unpacked and choose:\n\n' +
                                   str(SOURCE / 'extension') + '\n\nExpected ID: hagjmolifioccmojhoplpopjklljajno')
        dialog.connect('response', lambda d, *_: d.destroy())
        dialog.present()

    def close(self, *_):
        if self.recovering:
            self.status.set_text('Please keep this window open until the recovery attempt finishes.')
            return True
        self.cancel_work()
        self.items.clear()
        self.saved_password.get_delegate().set_visibility(False)
        self.saved_password.set_text('')
        self.password.set_text('')
        return False


if __name__ == '__main__':
    Passwords().run()
