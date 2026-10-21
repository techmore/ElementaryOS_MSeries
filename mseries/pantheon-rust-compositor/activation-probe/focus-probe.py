"""Popup grab, override-redirect and attention checks (defects D1, D2, D3, D8).

  popup      B opens its menu (an xdg_popup grab) with a real click, then the compositor
             focuses A over D-Bus. Typed keys must reach A and the menu must close.
  orcard     A has focus; an X11 notification card (override-redirect, no input) maps and
             is clicked. A must stay active with the keyboard, and the click must reach the
             card. Then a burst of short-lived cards counts xwm BadWindow errors.
  attention  (run with the strict policy) A calls present() without input while B has
             focus: A must be marked demands-attention, and focusing A clears it. Then an
             X11 window sets WM_HINTS urgency while unfocused: marked, then cleared on focus.

Client A is this process (a GTK 4 window with an entry). Prints one RESULT line.
"""
import json
import os
import re
import subprocess
import sys
import time

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

MODE = sys.argv[1]
HOST = dict(os.environ, DISPLAY=os.environ['HOST_DISPLAY'])
HERE = os.environ['PROBE_DIR']
RUN = os.environ['XDG_RUNTIME_DIR']
A_FILE, B_FILE, CARD_FILE = (os.path.join(RUN, name) for name in ('a.json', 'b.json', 'card.txt'))


def raw_windows():
    return subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.pantheon.gala',
                           '--object-path', '/org/pantheon/gala/DesktopInterface',
                           '--method', 'org.pantheon.gala.DesktopIntegration.GetWindows'],
                          capture_output=True, text=True).stdout


def windows():
    out = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.pantheon.gala',
                          '--object-path', '/org/pantheon/gala/DesktopInterface',
                          '--method', 'org.pantheon.gala.DesktopIntegration.GetWindows'],
                         capture_output=True, text=True).stdout
    found = {}
    for chunk in out.split('), ('):
        title = re.search(r"'title': <'([^']*)'>", chunk)
        # GVariant prints the "uint64" annotation only before the first uid.
        uid = re.search(r'(?:uint64 )?(\d+), \{', chunk)
        if title and uid:
            found[title.group(1)] = {
                'uid': int(uid.group(1)),
                'focus': "'has-focus': <true>" in chunk,
                'attention': "'demands-attention': <true>" in chunk,
            }
    return found


def focus(title):
    uid = windows()[title]['uid']
    subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.pantheon.gala',
                    '--object-path', '/org/pantheon/gala/DesktopInterface',
                    '--method', 'org.pantheon.gala.DesktopIntegration.FocusWindow', str(uid)],
                   capture_output=True)


def host_xdotool(*args):
    subprocess.run(['xdotool', *args], env=HOST, capture_output=True)


def focus_nested_window():
    wins = subprocess.run(['xdotool', 'search', '--pid', os.environ['COMP_PID']],
                          env=HOST, capture_output=True, text=True).stdout.split()
    for w in wins:
        host_xdotool('windowfocus', w)


def xwayland_env():
    log = open(os.environ['LOG'], errors='replace').read()
    match = re.findall(r'display_number\D{0,12}(\d+)', re.sub(r'\x1b\[[0-9;]*m', '', log))
    if not match:
        return None
    env = {k: v for k, v in os.environ.items() if k != 'WAYLAND_DISPLAY'}
    env.update(DISPLAY=':' + match[-1], GDK_BACKEND='x11')
    return env


def read_json(path):
    try:
        return json.load(open(path))
    except (OSError, ValueError):
        return {}


def bad_windows():
    """xwm BadWindow errors (code 3) on ChangeProperty (opcode 18), per window id.

    Activating a card set _NET_WM_STATE_FOCUSED on it and the next focus change
    cleared it, often after the client had destroyed it: 3-4 errors per
    short-lived card before the fix. Smithay's own map handling still writes
    about 2 per card destroyed while mapping, with or without focus changes;
    that remainder is reported, not gated."""
    log = open(os.environ['LOG'], errors='replace').read()
    counts = {}
    for window in re.findall(r'error_code: 3, [^}]*bad_value: (\d+), [^}]*major_opcode: 18,', log):
        counts[window] = counts.get(window, 0) + 1
    return counts


class App(Gtk.Application):
    def do_activate(self):
        self.a = Gtk.ApplicationWindow(application=self, title='probe-A', default_width=320, default_height=160)
        self.entry = Gtk.Entry()
        self.a.set_child(self.entry)
        self.a.present()
        self.entry.grab_focus()
        self.children = []
        GLib.timeout_add(100, self.save)
        GLib.timeout_add(1200, getattr(self, 'start_' + MODE))

    def save(self):
        with open(A_FILE, 'w') as out:
            json.dump({'entry': self.entry.get_text(), 'active': self.a.is_active()}, out)
        return True

    def spawn(self, args, env=None):
        self.children.append(subprocess.Popen(args, env=env))

    def later(self, ms, fn):
        GLib.timeout_add(ms, lambda: fn() and False)

    def when(self, condition, then, what, limit=15):
        """Poll `condition` every 150 ms (startup is slow on a loaded machine)."""
        started = time.monotonic()

        def poll():
            if condition():
                then()
                return False
            if time.monotonic() - started > limit:
                self.finish('%s: timed out waiting for %s (%s)' % (MODE, what, raw_windows().strip()))
                return False
            return True
        GLib.timeout_add(150, poll)

    def finish(self, text):
        print('RESULT ' + text, flush=True)
        for child in self.children:
            child.kill()
        self.quit()
        return False

    # D1 + D8 ---------------------------------------------------------------
    def start_popup(self):
        self.spawn([sys.executable, '-W', 'ignore', os.path.join(HERE, 'menu-client.py'), B_FILE])
        self.when(lambda: windows().get('probe-B', {}).get('focus') and os.path.exists(B_FILE),
                  lambda: self.later(500, self.popup_open_menu), 'B to take focus')
        return False

    def popup_open_menu(self):
        focus_nested_window()
        host_xdotool('mousemove', '640', '400')
        host_xdotool('click', '1')
        self.when(lambda: read_json(B_FILE).get('popover'), lambda: self.later(300, self.popup_focus_a),
                  'the menu to open', limit=5)

    def popup_focus_a(self):
        focus('probe-A')
        self.later(600, lambda: host_xdotool('key', '--delay', '80', 'x', 'y', 'z'))
        self.later(1800, self.popup_done)

    def popup_done(self):
        a, b = read_json(A_FILE), read_json(B_FILE)
        self.finish("popup: keys reached A=%r menu entry=%r menu closed=%s A active=%s"
                    % (a.get('entry'), b.get('entry'), not b.get('popover'), a.get('active')))

    # D2 --------------------------------------------------------------------
    def start_orcard(self):
        self.x11 = xwayland_env()
        if self.x11 is None:
            return self.finish('orcard: XWayland display not found in the compositor log')
        self.spawn([sys.executable, '-W', 'ignore', os.path.join(HERE, 'x11-client.py'), 'card', CARD_FILE], env=self.x11)
        self.when(lambda: os.path.exists(CARD_FILE + '.mapped') and windows().get('probe-A', {}).get('focus'),
                  lambda: self.later(500, self.orcard_click), 'the card to map')
        return False

    def orcard_click(self):
        self.active_before = read_json(A_FILE).get('active')
        focus_nested_window()
        host_xdotool('mousemove', '120', '80')
        host_xdotool('click', '1')
        self.later(600, lambda: host_xdotool('key', '--delay', '80', 'a', 'b', 'c'))
        self.later(1800, self.orcard_burst)

    def orcard_burst(self):
        a = read_json(A_FILE)
        self.card_result = ("orcard: A kept focus=%r A active before=%s after=%s card clicked=%s"
                            % (a.get('entry'), self.active_before, a.get('active'), os.path.exists(CARD_FILE)))
        self.bad_before = bad_windows()
        burst = subprocess.Popen([sys.executable, '-W', 'ignore', os.path.join(HERE, 'x11-client.py'), 'burst', '80'], env=self.x11)
        self.children.append(burst)

        def wait():
            # Every focus change deactivates all other windows, which touched
            # _NET_WM_STATE on cards that were already gone.
            if not os.environ.get('BURST_NO_FOCUS'):
                focus('probe-A')
            if burst.poll() is None:
                return True
            def report():
                counts = {w: n for w, n in bad_windows().items() if w not in self.bad_before}
                beyond = sum(max(0, n - 2) for n in counts.values())
                self.finish(self.card_result + ' | ChangeProperty BadWindow: %d on %d cards, %d beyond 2 per card'
                            % (sum(counts.values()), len(counts), beyond))
            self.later(800, report)
            return False
        GLib.timeout_add(60, wait)

    # D3 --------------------------------------------------------------------
    def start_attention(self):
        self.spawn([sys.executable, '-W', 'ignore', os.path.join(HERE, 'typing-client.py'), B_FILE])
        self.when(lambda: windows().get('probe-B', {}).get('focus'), lambda: self.later(500, self.attention_present),
                  'B to take focus')
        return False

    def attention_present(self):
        self.t0 = time.monotonic()
        self.a.present()
        GLib.timeout_add(100, self.attention_poll_marked)

    def attention_poll_marked(self):
        a = windows().get('probe-A', {})
        if a.get('focus'):
            return self.finish('attention: A was raised, the policy should have refused it')
        if a.get('attention'):
            self.marked_ms = (time.monotonic() - self.t0) * 1000
            focus('probe-A')
            self.later(500, self.attention_cleared)
            return False
        if time.monotonic() - self.t0 > 4:
            return self.finish('attention: A was never marked demands-attention (%s)' % a)
        return True

    def attention_cleared(self):
        a = windows().get('probe-A', {})
        self.wayland_result = 'attention: marked=True after %.0f ms cleared=%s' % (
            self.marked_ms, a.get('focus') and not a.get('attention'))
        self.x11 = xwayland_env()
        if self.x11 is None:
            return self.finish(self.wayland_result + ' | x11: XWayland display not found')
        self.spawn([sys.executable, '-W', 'ignore', os.path.join(HERE, 'x11-client.py'), 'urgent', '3500'], env=self.x11)
        self.t1 = time.monotonic()
        GLib.timeout_add(150, self.attention_wait_x11)

    def attention_wait_x11(self):
        # The X11 window takes focus when it maps; give focus back to A so the
        # urgency hint arrives while it is in the background.
        if 'probe-X' in windows():
            focus('probe-A')
            GLib.timeout_add(150, self.attention_poll_x11)
            return False
        if time.monotonic() - self.t1 > 15:
            return self.finish(self.wayland_result + ' | x11 window never mapped')
        return True

    def attention_poll_x11(self):
        x = windows().get('probe-X', {})
        if x.get('attention'):
            focus('probe-X')
            self.later(500, lambda: self.finish(self.wayland_result + ' | x11 urgent marked=True cleared=%s' % (
                not windows().get('probe-X', {}).get('attention'))))
            return False
        if time.monotonic() - self.t1 > 25:
            return self.finish(self.wayland_result + ' | x11 urgent never marked (%s)' % x)
        return True


App(application_id='ms.nested.probe').run([])
