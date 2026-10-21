#!/usr/bin/python3
"""Real X input against production App/Launcher on a private display and D-Bus."""
import argparse
import json
import os
from pathlib import Path
import subprocess as sp
import sys
import tempfile
import time


def waitfor(fn, seconds=10):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        try:
            value = fn()
            if value:
                return value
        except (FileNotFoundError, ValueError, KeyError):
            pass
        time.sleep(.05)
    raise AssertionError('Timed out waiting for fixture state')


def portal_service():
    # Answer GTK's synchronous settings queries from a separate private process.
    from gi.repository import Gio, GLib
    xml = '<node><interface name="org.freedesktop.portal.Settings"><method name="Read"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method><method name="ReadOne"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="v" direction="out"/></method><method name="ReadAll"><arg type="as" direction="in"/><arg type="a{sa{sv}}" direction="out"/></method></interface></node>'
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    appearance = {
        'color-scheme': GLib.Variant('u', 0),
        'accent-color': GLib.Variant('(ddd)', (0.21, 0.54, 0.90)),
        'contrast': GLib.Variant('u', 0),
    }
    def call(connection, sender, path, interface, method, params, invocation):
        if method == 'ReadAll':
            import fnmatch
            patterns, = params.unpack()
            values = {'org.freedesktop.appearance': appearance} if not patterns or '' in patterns or any(
                fnmatch.fnmatchcase('org.freedesktop.appearance', pattern) for pattern in patterns) else {}
            invocation.return_value(GLib.Variant('(a{sa{sv}})', (values,)))
        else:
            namespace, key = params.unpack()
            if namespace != 'org.freedesktop.appearance' or key not in appearance:
                invocation.return_dbus_error('org.freedesktop.portal.Error.NotFound', 'Unknown fixture setting')
            else:
                # Deprecated Read preserves the portal's historical double boxing;
                # ReadOne is the corrected API with a single variant layer.
                value = GLib.Variant('v', appearance[key]) if method == 'Read' else appearance[key]
                invocation.return_value(GLib.Variant('(v)', (value,)))
    connection.register_object('/org/freedesktop/portal/desktop', Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0], call, None, None)
    connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'RequestName', GLib.Variant('(su)', ('org.freedesktop.portal.Desktop', 0)), None, Gio.DBusCallFlags.NONE, 5000, None)
    appcenter_xml = '<node><interface name="io.elementary.appcenter"><method name="GetComponentFromDesktopId"><arg type="s" direction="in"/><arg type="s" direction="out"/></method><method name="SearchComponents"><arg type="s" direction="in"/><arg type="as" direction="out"/></method></interface></node>'
    def appcenter_call(connection, sender, path, interface, method, params, invocation):
        invocation.return_value(GLib.Variant('(s)', ('',)) if method == 'GetComponentFromDesktopId' else GLib.Variant('(as)', ([],)))
    connection.register_object('/io/elementary/appcenter', Gio.DBusNodeInfo.new_for_xml(appcenter_xml).interfaces[0], appcenter_call, None, None)
    connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'RequestName', GLib.Variant('(su)', ('io.elementary.appcenter', 0)), None, Gio.DBusCallFlags.NONE, 5000, None)
    # The fixture's logical system bus is this same private no-activation bus.
    # A real Launcher consults these read-only properties while constructing menus.
    switcheroo_xml = '<node><interface name="net.hadess.SwitcherooControl"><property name="HasDualGpu" type="b" access="read"/><property name="GPUs" type="aa{sv}" access="read"/></interface></node>'
    gpu_properties = {'HasDualGpu': GLib.Variant('b', False), 'GPUs': GLib.Variant('aa{sv}', [])}
    def gpu_property(connection, sender, path, interface, prop):
        return gpu_properties[prop]
    connection.register_object('/net/hadess/SwitcherooControl', Gio.DBusNodeInfo.new_for_xml(switcheroo_xml).interfaces[0], None, gpu_property, None)
    connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus', 'org.freedesktop.DBus', 'RequestName', GLib.Variant('(su)', ('net.hadess.SwitcherooControl', 0)), None, Gio.DBusCallFlags.NONE, 5000, None)
    Path(os.environ['QUAL_PORTAL_READY']).touch()
    GLib.MainLoop().run()


def inside(binary, output, theme):
    os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS']
    assert os.environ['GDK_BACKEND'] == 'x11'
    assert os.environ.get('QUAL_PRIVATE') == '1'
    assert os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY')
    statefile = Path(os.environ['QUAL_STATE'])
    def state():
        return json.loads(statefile.read_text())
    def command(*args):
        return sp.check_output(args, text=True, timeout=15).strip()
    log = (output / (theme + '.log')).open('w')
    portal = sp.Popen([sys.executable, __file__, '--portal'], stdout=log, stderr=sp.STDOUT)
    waitfor(lambda: Path(os.environ['QUAL_PORTAL_READY']).exists())
    process = sp.Popen([binary, theme], stdout=log, stderr=sp.STDOUT)
    try:
        waitfor(lambda: state().get('focused_entry'))
        wid = command('xdotool', 'search', '--name', '^PR343 qualification$').splitlines()[0]
        origin = dict(line.split('=') for line in command('xdotool', 'getwindowgeometry', '--shell', wid).splitlines())
        command('xdotool', 'windowfocus', wid)
        def move(name):
            current=state()
            x, y, w, h = current[name]
            sx,sy=current['surface_offset']
            x+=sx
            y+=sy
            command('xdotool', 'mousemove', str(int(origin['X']) + int(x+w/2)), str(int(origin['Y']) + int(y+h/2)))
        def click(name, button=1):
            move(name)
            command('xdotool', 'click', str(button))
        markers = state()['markers']
        assert [m['visible'] for m in markers] == [True, True, True, False], markers
        assert [m['focused'] for m in markers] == [False, True, False, False], markers
        # Cross into the actual launcher tooltip without taking keyboard focus.
        move('teams')
        time.sleep(.8)
        assert state()['focused_entry']
        command('xdotool', 'type', '--clearmodifiers', 'hover-keeps-typing')
        waitfor(lambda: Path(os.environ['QUAL_TYPED']).read_text() == 'hover-keeps-typing')
        move('entry')
        click('teams')
        waitfor(lambda: 'focus:101' in Path(os.environ['QUAL_EVENTS']).read_text())
        click('outlook')
        waitfor(lambda: 'show:brave-outlook.office.com__mail_-Default' in Path(os.environ['QUAL_EVENTS']).read_text())
        click('transient')
        waitfor(lambda: 'focus:301' in Path(os.environ['QUAL_EVENTS']).read_text())
        events = Path(os.environ['QUAL_EVENTS']).read_text().splitlines()
        assert not any(e.startswith('show:') and 'teams' in e.lower() for e in events), events
        # Real secondary clicks and Escape exercise native popover grabs.
        click('transient', 3)
        waitfor(lambda: state()['menus'][2])
        labels = (output / 'transient-menu.txt').read_text()
        for invalid in ['Keep in Dock', 'Uninstall', 'View in AppCenter']:
            assert invalid not in labels, labels
        command('xdotool', 'key', 'Escape')
        waitfor(lambda: not state()['menus'][2])
        click('teams', 3)
        waitfor(lambda: state()['menus'][0])
        assert 'Keep in Dock' in (output / 'teams-menu.txt').read_text()
        command('xdotool', 'key', 'Escape')
        waitfor(lambda: not state()['menus'][0])
        click('entry')
        command('xdotool', 'key', 'ctrl+a')
        command('xdotool', 'type', '--clearmodifiers', 'typing-after-menu-and-activation')
        waitfor(lambda: Path(os.environ['QUAL_TYPED']).read_text() == 'typing-after-menu-and-activation')
        move('entry')
        time.sleep(.3)
        # Capture the actual fixture window, without resizing or editing pixels.
        command('ffmpeg', '-nostdin', '-loglevel', 'error', '-f', 'x11grab', '-video_size', origin['WIDTH']+'x'+origin['HEIGHT'],
                '-i', os.environ['DISPLAY']+'+'+origin['X']+','+origin['Y'], '-frames:v', '1', '-update', '1', '-y', str(output/(theme+'.png')))
        report = {'theme': theme, 'markers': markers, 'events': events, 'pointer_hover_preserves_typing': True,
                  'mixed_alias_activation_focuses_window': True, 'homogeneous_alias_activation_uses_full_group': True,
                  'transient_menu_hides_invalid_actions': True, 'native_context_menu_escape': True, 'typing_after_actions': True}
        (output/(theme+'.json')).write_text(json.dumps(report, indent=2)+'\n')
        print('PASS production launcher pointer, activation, menus, Escape and typing:', theme)
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except sp.TimeoutExpired:
            process.kill()
            process.wait()
        portal.terminate()
        portal.wait(timeout=5)
        log.close()


def main():
    if sys.argv[1:] == ['--portal']:
        portal_service()
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('binary')
    parser.add_argument('output')
    parser.add_argument('--inside', choices=['light', 'dark'])
    args = parser.parse_args()
    binary = str(Path(args.binary).resolve())
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.inside:
        inside(binary, output, args.inside)
        return
    for theme in ['light', 'dark']:
        for suffix in ['png', 'json']:
            (output/(theme+'.'+suffix)).unlink(missing_ok=True)
        with tempfile.TemporaryDirectory(prefix='dock-input-qualification-', ignore_cleanup_errors=True) as scratch:
            home = Path(scratch)
            apps = home/'.local/share/applications'
            apps.mkdir(parents=True)
            tools = home/'.local/bin'
            tools.mkdir(parents=True)
            helper = tools/'codexbar-linux'
            helper.write_text('#!/bin/sh\nprintf \'{"entries":[]}\'\n')
            helper.chmod(0o755)
            # Original fixture artwork: no downloaded/redistributed vendor logos.
            icons = home/'.local/share/icons/hicolor/scalable/apps'
            icons.mkdir(parents=True)
            for name, color in [('teams', '#6264a7'), ('outlook', '#1676b7'), ('closed', '#399d72'), ('application-default-icon', '#737b83')]:
                (icons/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect x="4" y="4" width="56" height="56" rx="10" fill="'+color+'"/><path d="M18 22h28v20H30l-8 6v-6h-4z" fill="white"/></svg>')
            for name, identity, icon in [('TeamsFixture','brave-teams.microsoft.com__v2_-Default','teams'),
                                         ('OutlookFixture','brave-outlook.office.com__mail_-Default','outlook'),
                                         ('ClosedFixture','ClosedFixture','closed')]:
                (apps/(name+'.desktop')).write_text('[Desktop Entry]\nType=Application\nName='+name+'\nExec=/usr/bin/false\nIcon='+str(icons/(icon+'.svg'))+'\nStartupWMClass='+identity+'\n')
            runtime = home/'runtime'
            runtime.mkdir(mode=0o700)
            env = {**os.environ, 'HOME': str(home), 'XDG_CONFIG_HOME': str(home/'config'), 'XDG_CACHE_HOME': str(home/'cache'),
                   'XDG_DATA_HOME': str(home/'.local/share'), 'XDG_RUNTIME_DIR': str(runtime), 'GSETTINGS_BACKEND': 'memory', 'GIO_USE_VFS': 'local', 'GIO_USE_VOLUME_MONITOR': 'unix',
                   'GDK_BACKEND': 'x11', 'GSK_RENDERER': 'cairo', 'GTK_A11Y': 'none', 'GTK_USE_PORTAL': '0', 'LC_ALL': 'C.UTF-8',
                   'QUAL_PRIVATE': '1', 'QUAL_PORTAL_READY': str(home/'portal-ready'), 'QUAL_OUT': str(output), 'QUAL_STATE': str(home/'state.json'), 'QUAL_TYPED': str(home/'typed'),
                   'QUAL_EVENTS': str(home/'events'), 'GTK_THEME': 'io.elementary.stylesheet.blueberry'+(':dark' if theme=='dark' else '')}
            for key in ['DISPLAY', 'WAYLAND_DISPLAY', 'WAYLAND_SOCKET', 'DBUS_SESSION_BUS_ADDRESS']:
                env.pop(key, None)
            bus_config = home / 'bus.conf'
            bus_config.write_text('<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen>'
                '<policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>')
            sp.run(['dbus-run-session', '--config-file=' + str(bus_config), '--', 'xvfb-run', '-a', '-s', '-screen 0 1280x900x24', sys.executable, __file__, binary, str(output), '--inside', theme], env=env, check=True)


if __name__ == '__main__':
    main()
