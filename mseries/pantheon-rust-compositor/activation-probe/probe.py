"""Client A (no recent input) calls present() while a DIFFERENT client B has focus and the user types into it."""
import os, subprocess, sys, time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

MODE = sys.argv[1]            # idle | typing
HOST_DISPLAY = os.environ['HOST_DISPLAY']
S = os.environ['PROBE_DIR']
BFILE = os.path.join(os.environ['XDG_RUNTIME_DIR'], 'b-received.txt')

def windows():
    out = subprocess.run(['gdbus', 'call', '--session', '--dest', 'org.pantheon.gala', '--object-path', '/org/pantheon/gala/DesktopInterface',
                          '--method', 'org.pantheon.gala.DesktopIntegration.GetWindows'], capture_output=True, text=True).stdout
    return out.split('), (')

def focused_title():
    for w in windows():
        if "'has-focus': <true>" in w:
            for title in ('probe-A', 'probe-B'):
                if "'%s'" % title in w:
                    return title
    return 'none'

class App(Gtk.Application):
    def do_activate(self):
        self.a = Gtk.ApplicationWindow(application=self, title='probe-A', default_width=320, default_height=160)
        self.a.set_child(Gtk.Label(label='A'))
        self.a.present()
        GLib.timeout_add(1200, self.open_b)

    def open_b(self):
        self.b = subprocess.Popen([sys.executable, '-W', 'ignore', os.path.join(S, 'typing-client.py'), BFILE])
        GLib.timeout_add(2500, self.begin)
        return False

    def begin(self):
        print('setup: focus is on', focused_title(), flush=True)
        self.typing = None
        env = dict(os.environ, DISPLAY=HOST_DISPLAY)
        if MODE == 'typing':
            wins = subprocess.run(['xdotool', 'search', '--pid', os.environ['COMP_PID']], env=env, capture_output=True, text=True).stdout.split()
            for w in wins:
                subprocess.run(['xdotool', 'windowfocus', w], env=env, capture_output=True)
            subprocess.run(['xdotool', 'mousemove', '600', '400'], env=env)
            # ~3 s of steady typing (every 120 ms) into the other client
            self.typing = subprocess.Popen(['xdotool', 'key', '--delay', '120'] + ['a'] * 25, env=env)
            self.typing_started = time.monotonic()
            GLib.timeout_add(600, self.call_present)
        else:
            self.call_present()
        return False

    def call_present(self):
        self.t_present = time.monotonic()
        self.a.present()
        GLib.timeout_add(100, self.poll)
        return False

    def finish(self, text):
        received = open(BFILE).read() if os.path.exists(BFILE) else ''
        print(text + ' | B had received %d keystrokes' % len(received), flush=True)
        self.b.kill()
        self.quit()

    def poll(self):
        now = time.monotonic()
        who = focused_title()
        if who == 'probe-A':
            note = ''
            if self.typing is not None:
                note = ' | %.1fs after typing began' % (now - self.typing_started) + (', typing still running' if self.typing.poll() is None else ', typing already finished')
            self.finish('RESULT focused=A after %.0f ms%s' % ((now - self.t_present) * 1000, note)); return False
        if now - self.t_present > 9:
            self.finish('RESULT focused=%s (A never raised in 9s)' % who); return False
        return True

App(application_id='ms.nested.probe').run([])
