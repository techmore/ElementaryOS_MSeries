#!/usr/bin/python3
"""Run the native cached-widget fixture with typed portal replies and no host system bus."""
import os
from pathlib import Path
import subprocess
import sys
import time

from gi.repository import Gio, GLib


def main():
    runtime = Path(os.environ['XDG_RUNTIME_DIR'])
    assert os.environ.get('DBUS_SESSION_BUS_ADDRESS')
    assert os.environ.get('G_DEBUG') == 'fatal-criticals'
    # This address is established by the caller's fresh dbus-run-session. Never
    # inherit the owner's system bus, even when it exists on a development host.
    os.environ['DBUS_SYSTEM_BUS_ADDRESS'] = os.environ['DBUS_SESSION_BUS_ADDRESS']
    schemas = Gio.SettingsSchemaSource.get_default()
    installed, relocatable = schemas.list_schemas(True)
    expected = {'io.elementary.dock', 'io.elementary.dock.keybindings',
                'org.techmore.mseries.dock', 'io.elementary.desktop.wm.keybindings'}
    assert set(installed) | set(relocatable) == expected, (installed, relocatable)
    assert not relocatable
    keybindings = Gio.Settings.new('io.elementary.desktop.wm.keybindings')
    assert keybindings.get_strv('switch-to-workspace-last') == ['<Super>End', '<Super>0']
    print('PASS: exact four-schema private inventory; pinned Gala key type/default; no host schemas', flush=True)
    ready = runtime / 'portal-ready'
    portal = subprocess.Popen([sys.executable, str(Path(__file__).with_name('test-launcher-qualification.py')), '--portal'],
                              env={**os.environ, 'QUAL_PORTAL_READY': str(ready)})
    try:
        deadline = time.monotonic() + 10
        while not ready.exists():
            assert portal.poll() is None, 'Fixture portal exited before readiness'
            assert time.monotonic() < deadline, 'Fixture portal did not become ready'
            time.sleep(0.02)
        connection = Gio.bus_get_sync(Gio.BusType.SESSION)
        def read(method, namespace, key):
            result = connection.call_sync('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                'org.freedesktop.portal.Settings', method, GLib.Variant('(ss)', (namespace, key)),
                GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 3000, None)
            value = result.get_child_value(0).get_variant()
            if method == 'Read':
                assert value.get_type_string() == 'v'
                value = value.get_variant()
            return value
        # Granite 7.8.0/7.8.1 requests both of these exact, different variant types.
        for method in ['Read', 'ReadOne']:
            scheme = read(method, 'org.freedesktop.appearance', 'color-scheme')
            assert scheme.get_type_string() == 'u' and scheme.get_uint32() == 0
            accent = read(method, 'org.freedesktop.appearance', 'accent-color')
            assert accent.get_type_string() == '(ddd)' and accent.unpack() == (0.21, 0.54, 0.90)
        for patterns, present in [([], True), ([''], True), (['org.freedesktop.*'], True), (['unknown.*'], False)]:
            namespaces = connection.call_sync('org.freedesktop.portal.Desktop', '/org/freedesktop/portal/desktop',
                'org.freedesktop.portal.Settings', 'ReadAll', GLib.Variant('(as)', (patterns,)),
                GLib.VariantType('(a{sa{sv}})'), Gio.DBusCallFlags.NONE, 3000, None).get_child_value(0)
            appearance = namespaces.lookup_value('org.freedesktop.appearance', GLib.VariantType('a{sv}'))
            assert (appearance is not None) == present
            if present:
                assert appearance.lookup_value('color-scheme', None).get_type_string() == 'u'
                assert appearance.lookup_value('accent-color', None).get_type_string() == '(ddd)'
        try:
            read('Read', 'unknown.namespace', 'unknown-key')
        except GLib.Error as error:
            assert Gio.DBusError.get_remote_error(error) == 'org.freedesktop.portal.Error.NotFound'
        else:
            raise AssertionError('Unknown portal settings must fail explicitly')
        gpu = connection.call_sync('net.hadess.SwitcherooControl', '/net/hadess/SwitcherooControl',
            'org.freedesktop.DBus.Properties', 'Get', GLib.Variant('(ss)', ('net.hadess.SwitcherooControl', 'HasDualGpu')),
            GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 3000, None).get_child_value(0).get_variant()
        assert gpu.get_type_string() == 'b' and not gpu.get_boolean()
        gpus = connection.call_sync('net.hadess.SwitcherooControl', '/net/hadess/SwitcherooControl',
            'org.freedesktop.DBus.Properties', 'Get', GLib.Variant('(ss)', ('net.hadess.SwitcherooControl', 'GPUs')),
            GLib.VariantType('(v)'), Gio.DBusCallFlags.NONE, 3000, None).get_child_value(0).get_variant()
        assert gpus.get_type_string() == 'aa{sv}' and gpus.n_children() == 0
        assert not connection.call_sync('org.freedesktop.DBus', '/org/freedesktop/DBus',
            'org.freedesktop.DBus', 'NameHasOwner', GLib.Variant('(s)', ('org.freedesktop.Accounts',)),
            GLib.VariantType('(b)'), Gio.DBusCallFlags.NONE, 3000, None).unpack()[0]
        print('PASS: typed private portal and Switcheroo replies; unknown key fails; no Accounts service; host system bus excluded', flush=True)
        subprocess.run(['xvfb-run', '-a', sys.argv[1]], check=True, timeout=30)
    finally:
        portal.terminate()
        try:
            portal.wait(timeout=5)
        except subprocess.TimeoutExpired:
            portal.kill()
            portal.wait()


if __name__ == '__main__':
    main()
