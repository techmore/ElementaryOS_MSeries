#!/usr/bin/python3
"""Qualify the production dock on nested Wayland, never the owner's display/bus."""
import os
from pathlib import Path
import shutil
import signal
import subprocess as sp
import sys
import tempfile
import time


def fixture():
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
    app = Gtk.Application(application_id='org.techmore.DockTransitionFixture')
    app.connect('activate', lambda app: Gtk.ApplicationWindow(
        application=app, title='Dock transition fixture', default_width=320,
        default_height=200).present())
    app.run([])


def inside(binary, output):
    output = Path(output)
    env = os.environ | {'WAYLAND_DEBUG': '1', 'GDK_BACKEND': 'wayland',
                        'GTK_A11Y': 'none', 'GSK_RENDERER': 'cairo'}
    dock = None
    window = None
    def setting(mode):
        sp.run(['gsettings', 'set', 'io.elementary.dock', 'taskbar-mode',
                str(mode).lower()], check=True)
    def running():
        result = sp.run(['gdbus', 'call', '--session', '--dest', 'io.elementary.dock',
                         '--object-path', '/io/elementary/dock', '--method',
                         'io.elementary.dock.items.ListRunningApps'],
                        capture_output=True, text=True)
        return result.stdout if result.returncode == 0 else None
    def waitfor(predicate):
        deadline = time.monotonic() + 10
        while not predicate():
            assert dock.poll() is None, 'Dock exited during transition'
            assert time.monotonic() < deadline, 'Timed out waiting for window tracking'
            time.sleep(.1)
    try:
        setting(True)
        with (output / 'dock-protocol.log').open('w') as log:
            dock = sp.Popen([binary], env=env, stdout=log, stderr=log)
            waitfor(lambda: running() is not None)
            window = sp.Popen([sys.executable, __file__, '--fixture'], env=env)
            identity = 'org.techmore.DockTransitionFixture.desktop'
            waitfor(lambda: identity in (running() or ''))
            if os.environ.get('MSERIES_DOCK_CAPTURE_DISPLAY'):
                sp.run(['ffmpeg', '-loglevel', 'error', '-f', 'x11grab', '-video_size',
                        '1920x1080', '-i', os.environ['MSERIES_DOCK_CAPTURE_DISPLAY'],
                        '-frames:v', '1', '-update', '1', '-y', str(output / 'taskbar.png')], check=True)
            for mode in (False, True, False, True):
                setting(mode)
                for _ in range(15):
                    time.sleep(.1)
                    assert dock.poll() is None, f'Dock exited switching taskbar-mode={mode}'
                assert identity in (running() or ''), 'Open window disappeared from dock model'
            window.terminate()
            window.wait(timeout=5)
            window = None
            waitfor(lambda: identity not in (running() or identity))
            (output / 'result.txt').write_text(
                'PASS same dock survives four Wayland layout transitions; '
                'open app remains tracked and is removed after closing\n')
    finally:
        for child in (window, dock):
            if child is not None and child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
        # End only the private compositor that launched this child.
        os.kill(os.getppid(), signal.SIGTERM)


def main():
    if sys.argv[1:] == ['--fixture']:
        fixture()
        return
    if sys.argv[1] == '--inside':
        inside(sys.argv[2], sys.argv[3])
        return
    binary, schemas, output = map(lambda p: str(Path(p).resolve()), sys.argv[1:4])
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    assert shutil.which('pantheon-compositor'), 'Installed nested compositor required'
    with tempfile.TemporaryDirectory(prefix='dock-wayland-') as temporary:
        home = Path(temporary)
        runtime = home / 'runtime'
        runtime.mkdir(mode=0o700)
        apps = home / 'data/applications'
        apps.mkdir(parents=True)
        (apps / 'org.techmore.DockTransitionFixture.desktop').write_text(
            '[Desktop Entry]\nType=Application\nName=Dock transition fixture\n'
            'Exec=/usr/bin/false\nIcon=application-default-icon\n')
        bus = home / 'bus.conf'
        bus.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                       '<policy context="default"><allow send_destination="*"/>'
                       '<allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
        env = os.environ | {'HOME': str(home), 'XDG_CONFIG_HOME': str(home / 'config'),
            'XDG_DATA_HOME': str(home / 'data'), 'XDG_STATE_HOME': str(home / 'state'),
            'XDG_CACHE_HOME': str(home / 'cache'), 'XDG_RUNTIME_DIR': str(runtime),
            'GSETTINGS_BACKEND': 'keyfile', 'GSETTINGS_SCHEMA_DIR': schemas,
            'WINIT_UNIX_BACKEND': 'x11', 'LIBGL_ALWAYS_SOFTWARE': '1',
            'GIO_USE_VFS': 'local', 'GTK_A11Y': 'none'}
        for key in ('WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'DISPLAY',
                    'DBUS_SESSION_BUS_ADDRESS', 'DBUS_SYSTEM_BUS_ADDRESS'):
            env.pop(key, None)
        # Private bus for both logical buses: never contact host system services.
        command = ['dbus-run-session', '--config-file=' + str(bus), '--',
                   'sh', '-c', 'export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"; exec "$@"',
                   'private-wayland', 'xvfb-run', '-a', '-s', '-screen 0 1920x1080x24',
                   'sh', '-c', 'export MSERIES_DOCK_CAPTURE_DISPLAY="$DISPLAY"; exec "$@"',
                   'capture-display', shutil.which('pantheon-compositor'), '--backend', 'nested', '--run',
                   sys.executable, str(Path(__file__).resolve()), '--inside', binary, str(output)]
        with (output / 'compositor.log').open('w') as log:
            process = sp.Popen(command, env=env, stdout=log, stderr=log, start_new_session=True)
            try:
                process.wait(timeout=45)
            finally:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                process.wait(timeout=5)
    assert (output / 'result.txt').exists(), f'Wayland trial failed; see {output}'
    print((output / 'result.txt').read_text(), end='')


if __name__ == '__main__':
    main()
