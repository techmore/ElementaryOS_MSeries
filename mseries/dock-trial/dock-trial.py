#!/usr/bin/python3
"""Bounded, explicit native dock trial with an independent systemd watchdog."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from gi.repository import Gio, GLib

HOME = Path.home()
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', HOME / '.config'))
STATE = Path(os.environ.get('XDG_STATE_HOME', HOME / '.local/state')) / 'mseries/dock-trial'
MARKER = CONFIG / 'mseries/dock/user-disabled'
UNITS = CONFIG / 'systemd/user'
SCRIPT = HOME / '.local/libexec/mseries-dock-trial'
OUTPUT = STATE / 'latest.json'
UNIT = 'pantheon-dock.service'
TIMER = 'mseries-dock-trial-stop.timer'
TITLE = 'One-minute dock safety test'
# Native dock icon size at the default step of the size system (#332).
DEFAULT_ICON_SIZE = 48


def size_system_dock(mode, fallback):
    """Dock token from the M-Series size system once it is adopted, else the old literal."""
    tool = shutil.which('mseries-ui-scale') or str(HOME / '.local/bin/mseries-ui-scale')
    try:
        result = subprocess.run([tool, '--dock-size', mode], capture_output=True, text=True, timeout=5, check=False)
        return int(result.stdout) if result.returncode == 0 else fallback
    except (OSError, ValueError, subprocess.SubprocessError):
        return fallback


def systemctl(*args, check=True):
    return subprocess.run(['systemctl', '--user', *args], check=check,
                          capture_output=True, text=True, timeout=12)


def desktop(method, parameters=None):
    return Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
        'org.pantheon.gala', '/org/pantheon/gala/DesktopInterface',
        'org.pantheon.gala.DesktopIntegration', method, parameters, None,
        Gio.DBusCallFlags.NONE, 2000, None).unpack()


def ready():
    try:
        result = Gio.bus_get_sync(Gio.BusType.SESSION, None).call_sync(
            'org.pantheon.gala', '/org/pantheon/gala/DesktopInterface',
            'org.freedesktop.DBus.Properties', 'Get', GLib.Variant('(ss)',
            ('org.pantheon.gala.DesktopIntegration', 'FocusRoutingVersion')),
            None, Gio.DBusCallFlags.NONE, 2000, None).unpack()[0]
        pid = int(systemctl('show', 'pantheon-rust-compositor@wayland.service',
                            '-p', 'MainPID', '--value').stdout.strip())
        binary = Path('/usr/bin/pantheon-compositor').read_bytes()
        running = Path(f'/proc/{pid}/exe').read_bytes()
        return result >= 1 and hashlib.sha256(binary).digest() == hashlib.sha256(running).digest()
    except Exception:
        return False


def restore():
    STATE.mkdir(parents=True, exist_ok=True)
    MARKER.parent.mkdir(parents=True, exist_ok=True)
    original = STATE / 'original-disabled-marker'
    if MARKER.exists():
        return
    content = original.read_bytes() if original.exists() else b'Disabled after bounded dock trial.\n'
    temporary = MARKER.with_name('user-disabled.trial-restore')
    temporary.write_bytes(content)
    temporary.replace(MARKER)


def stop():
    try:
        restore()  # Opt-out is back before stopping anything.
    finally:
        # A marker I/O failure must never prevent terminating the dock.
        try:
            systemctl('stop', TIMER, check=False)
        finally:
            systemctl('stop', UNIT, check=False)


def configure(seconds):
    if not 5 <= seconds <= 600:
        raise ValueError('Trial duration must be between 5 and 600 seconds')
    UNITS.mkdir(parents=True, exist_ok=True)
    dropin = UNITS / (UNIT + '.d')
    dropin.mkdir(exist_ok=True)
    (dropin / '90-bounded-trial.conf').write_text(
        '[Service]\nRestart=no\nRuntimeMaxSec=' + str(seconds) + 's\n'
        'TimeoutStopSec=3s\nKillMode=control-group\n'
        'ExecStopPost=/usr/bin/python3 ' + str(SCRIPT) + ' --restore\n')
    (UNITS / 'mseries-dock-trial-stop.service').write_text(
        '[Unit]\nDescription=Restore disabled dock state and stop the trial\n'
        '[Service]\nType=oneshot\nExecStart=/usr/bin/python3 ' + str(SCRIPT) + ' --stop\n')
    (UNITS / TIMER).write_text(
        '[Unit]\nDescription=Independent dock trial deadline\n'
        '[Timer]\nOnActiveSec=' + str(seconds) + 's\nAccuracySec=100ms\n'
        'Unit=mseries-dock-trial-stop.service\n')
    systemctl('daemon-reload')


def arm(seconds):
    if not ready():
        raise RuntimeError('The updated compositor has not loaded; log out and back in first')
    if systemctl('is-active', UNIT, check=False).stdout.strip() == 'active':
        raise RuntimeError('A dock is already active; stop it before starting a bounded trial')
    STATE.mkdir(parents=True, exist_ok=True)
    original = STATE / 'original-disabled-marker'
    if MARKER.exists():
        shutil.copy2(MARKER, original)
    configure(seconds)
    systemctl('reset-failed', UNIT, 'mseries-dock-trial-stop.service', check=False)
    systemctl('stop', TIMER, check=False)
    systemctl('start', TIMER)
    if systemctl('is-active', TIMER, check=False).stdout.strip() != 'active':
        raise RuntimeError('Independent stop timer did not arm; leaving the dock disabled')
    try:
        if MARKER.exists():
            MARKER.unlink()
        systemctl('start', UNIT)
        if systemctl('is-active', UNIT, check=False).stdout.strip() != 'active':
            raise RuntimeError('Dock did not become active')
    except Exception:
        stop()
        raise


def gui(seconds, after_login, dock_only=False, visible=False):
    if after_login:
        pending = STATE / 'pending-login-trial'
        if not pending.exists():
            return
        deadline = time.monotonic() + 40
        while not ready() and time.monotonic() < deadline:
            time.sleep(1)
        if not ready():
            OUTPUT.write_text(json.dumps({'status': 'not-started', 'reason': 'updated compositor unavailable'}, indent=2))
            return
        pending.unlink()
        autostart = CONFIG / 'autostart/mseries-dock-trial.desktop'
        if autostart.exists():
            autostart.unlink()
    elif not ready():
        raise RuntimeError('A fresh login is required before this trial')

    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk

    class Trial(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='org.techmore.DockSafetyTrial')
            self.record = {'status': 'ready', 'duration_seconds': seconds,
                           'started_at': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                           'focus_losses': 0, 'snapping': {}, 'typing': False,
                           'snapping_check': 'skipped-dock-only' if dock_only else 'required'}
            self.running = False
            self.step = 0
            self.started = None
            self.saved_preferences = None

        def save(self):
            OUTPUT.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT.write_text(json.dumps(self.record, indent=2) + '\n')

        def do_activate(self):
            self.window = Gtk.ApplicationWindow(application=self, title=TITLE)
            self.window.set_default_size(720, 400)
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14,
                          margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
            self.label = Gtk.Label(label='The updated compositor is loaded.\n' +
                ('Start runs the dock for at most ' if dock_only else
                 'Start checks snapping, then runs the dock for at most ') + str(seconds) + ' seconds.\n'
                'Please leave this test window focused while it runs.\n'
                'The dock stops automatically if focus moves away.', wrap=True)
            box.append(self.label)
            self.entry = Gtk.Entry(placeholder_text='The test writes a short phrase here; you can also type here.')
            box.append(self.entry)
            self.start_button = Gtk.Button(label='Start bounded dock trial' if dock_only else
                                           'Start snapping check and bounded dock trial')
            self.start_button.connect('clicked', self.begin)
            box.append(self.start_button)
            emergency = Gtk.Button(label='Stop dock now')
            emergency.connect('clicked', lambda *_: self.finish('stopped-by-user'))
            box.append(emergency)
            self.window.set_child(box)
            self.window.connect('close-request', self.close)
            self.window.present()
            self.save()

        def own_focus(self):
            windows = desktop('GetWindows')[0]
            focused = [(uid, props) for uid, props in windows if props.get('has-focus')]
            return len(focused) == 1 and focused[0][1].get('title') == TITLE

        def inject(self, *args):
            if not self.own_focus():
                raise RuntimeError('Test window lost focus; no keys injected')
            subprocess.run(['ydotool', *args], check=True, timeout=5,
                           env=os.environ | {'YDOTOOL_SOCKET': str(Path(os.environ['XDG_RUNTIME_DIR']) / '.ydotool_socket')})

        def chord(self, direction):
            options = Gio.Settings.new('org.gnome.desktop.input-sources').get_strv('xkb-options')
            # The owner's Command/Ctrl swap makes physical LeftCtrl produce Super.
            super_key = 29 if 'ctrl:swap_lwin_lctl' in options else 125
            self.inject('key', f'{super_key}:1', f'{direction}:1', f'{direction}:0', f'{super_key}:0')

        def begin(self, *_):
            if self.started is not None:
                return
            self.started = time.monotonic()
            self.start_button.set_sensitive(False)
            self.entry.grab_focus()
            self.label.set_label('Checking left/right snapping. Keep this window focused. The dock is still disabled.')
            GLib.timeout_add(600, self.start_dock if dock_only else self.preflight)

        def preflight(self):
            try:
                if not self.own_focus():
                    raise RuntimeError('Test window was not focused')
                if self.step == 0:
                    self.chord(105)
                elif self.step in (1, 2):
                    surface = self.window.get_surface()
                    monitor = surface.get_display().get_monitor_at_surface(surface).get_geometry()
                    width = self.window.get_width()
                    side = 'left' if self.step == 1 else 'right'
                    self.record['snapping'][side] = {'window_width': width, 'monitor_width': monitor.width,
                                                    'half_width_observed': abs(width - monitor.width / 2) <= 3}
                    if not self.record['snapping'][side]['half_width_observed']:
                        raise RuntimeError(side + ' half width did not match; dock left disabled')
                    if self.step == 1:
                        self.chord(106)
                    else:
                        self.entry.set_text('')
                        self.entry.grab_focus()
                        return self.start_dock()
                self.step += 1
                return True
            except Exception as error:
                self.record['error'] = str(error)
                self.finish('stopped-preflight')
                return False

        def start_dock(self):
            try:
                if not self.own_focus():
                    raise RuntimeError('Test window was not focused')
                if visible:
                    settings = Gio.Settings.new('io.elementary.dock')
                    self.saved_preferences = {key: settings.get_value(key) for key in
                                              ('autohide-mode', 'icon-size')}
                    settings.set_string('autohide-mode', 'never')
                    settings.set_int('icon-size', size_system_dock('native', DEFAULT_ICON_SIZE))
                    Gio.Settings.sync()
                arm(seconds)
                self.running = True
                self.dock_started = time.monotonic()
                self.record['status'] = 'dock-trial-running'
                GLib.timeout_add(200, self.watch)
                GLib.timeout_add(900, self.check_typing)
                self.save()
            except Exception as error:
                self.record['error'] = str(error)
                self.finish('stopped-dock-start')
            return False

        def check_typing(self):
            try:
                if self.running:
                    self.inject('type', '--key-delay=5', 'dock-focus-check')
                    GLib.timeout_add(500, self.verify_typing)
            except Exception as error:
                self.record['error'] = str(error)
                self.finish('stopped-typing-check')
            return False

        def verify_typing(self):
            self.record['typing'] = self.entry.get_text() == 'dock-focus-check'
            if not self.record['typing']:
                self.finish('stopped-text-delivery-failed')
            self.save()
            return False

        def watch(self):
            if not self.running:
                return False
            try:
                elapsed = time.monotonic() - self.dock_started
                if not self.own_focus():
                    self.record['focus_losses'] += 1
                    self.finish('stopped-focus-moved')
                    return False
                if elapsed >= seconds:
                    self.finish('completed-bounded-trial')
                    return False
                if systemctl('is-active', UNIT, check=False).stdout.strip() != 'active':
                    self.finish('dock-stopped-at-deadline' if elapsed >= seconds - 2 else 'dock-stopped-early')
                    return False
                self.label.set_label('Dock trial: ' + str(max(0, int(seconds - elapsed))) + ' seconds left.\n'
                    'Type in the field if you like. Moving focus away ends the trial immediately.')
                return True
            except Exception as error:
                self.record['error'] = str(error)
                self.finish('stopped-watch-error')
                return False

        def finish(self, reason):
            self.running = False
            stop()
            self.restore_preferences()
            if self.record['status'].startswith('stopped-') or self.record['status'] == 'completed-bounded-trial':
                return
            self.record['status'] = reason
            self.record['dock_inactive'] = systemctl('is-active', UNIT, check=False).stdout.strip() != 'active'
            self.record['disabled_marker_restored'] = MARKER.exists()
            self.save()
            self.label.set_label('Dock stopped; disabled state restored.\nResult: ' + reason + '\n'
                'Return to the chat to review the result or request a longer trial.')

        def restore_preferences(self):
            if self.saved_preferences is not None:
                settings = Gio.Settings.new('io.elementary.dock')
                for key, value in self.saved_preferences.items():
                    settings.set_value(key, value)
                Gio.Settings.sync()
                self.saved_preferences = None

        def close(self, *_):
            if self.running:
                self.finish('stopped-window-closed')
            self.restore_preferences()
            return False

    Trial().run([])


def main():
    global OUTPUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--restore', action='store_true')
    parser.add_argument('--stop', action='store_true')
    parser.add_argument('--configure', action='store_true')
    parser.add_argument('--after-login', action='store_true')
    parser.add_argument('--visible', action='store_true',
                        help='Temporarily use the native dock icon size (48 px at the default step) and no auto-hide')
    parser.add_argument('--dock-only', action='store_true',
                        help='Test dock focus and typing independently of snapping')
    args = parser.parse_args()
    if args.report:
        OUTPUT = args.report
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if args.restore:
        restore()
    elif args.stop:
        stop()
    elif args.configure:
        configure(args.seconds)
    else:
        gui(args.seconds, args.after_login, args.dock_only, args.visible)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        restore()
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
