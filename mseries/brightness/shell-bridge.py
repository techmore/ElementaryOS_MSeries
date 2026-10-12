#!/usr/bin/python3
"""Implement GNOME 50's brightness contract using Pantheon's Mutter backlight."""
import math
from gi.repository import Gio, GLib

NAME = 'org.gnome.Shell.Brightness'
PATH = '/org/gnome/Shell/Brightness'
XML = '''<node><interface name="org.gnome.Shell.Brightness">
<method name="SetDimming"><arg type="b" direction="in"/></method>
<method name="SetAutoBrightnessTarget"><arg type="d" direction="in"/></method>
<property name="HasBrightnessControl" type="b" access="read"/>
<signal name="BrightnessChanged"/>
</interface></node>'''


class Bridge:
    def __init__(self):
        self.settings = Gio.Settings.new('org.gnome.settings-daemon.plugins.power')
        self.display = Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SESSION,
            Gio.DBusProxyFlags.NONE, None, 'org.gnome.Mutter.DisplayConfig',
            '/org/gnome/Mutter/DisplayConfig', 'org.gnome.Mutter.DisplayConfig', None)
        self.bus = self.display.get_connection()
        self.saved = None
        self.last_set = None
        self.last_seen = None
        self.registration = self.bus.register_object(PATH,
            Gio.DBusNodeInfo.new_for_xml(XML).interfaces[0], self.method, self.property, None)
        self.owner = Gio.bus_own_name_on_connection(self.bus, NAME,
            Gio.BusNameOwnerFlags.NONE, None, None)
        self.display.connect('g-properties-changed', self.changed)

    def panel(self):
        result = self.bus.call_sync('org.gnome.Mutter.DisplayConfig',
            '/org/gnome/Mutter/DisplayConfig', 'org.freedesktop.DBus.Properties', 'Get',
            GLib.Variant('(ss)', ('org.gnome.Mutter.DisplayConfig', 'Backlight')),
            None, Gio.DBusCallFlags.NONE, 3000, None)
        serial, panels = result.unpack()[0]
        for panel in panels:
            if panel['connector'].startswith('eDP-') and panel['active']:
                return serial, panel
        raise ValueError('No active internal backlight')

    def set_value(self, serial, panel, value):
        target = max(panel['min'], min(panel['max'], round(value)))
        self.display.call_sync('SetBacklight', GLib.Variant('(usi)',
            (serial, panel['connector'], target)), Gio.DBusCallFlags.NONE, 3000, None)
        self.last_set = self.last_seen = target

    def dim(self, enable):
        if enable and not self.settings.get_boolean('idle-dim'):
            return
        if not enable and self.saved is None:
            return
        serial, panel = self.panel()
        if enable:
            if self.saved is None:
                self.saved = panel['value']
            target = min(self.saved, panel['max'] * self.settings.get_int('idle-brightness') / 100)
            self.set_value(serial, panel, target)
        else:
            # A user change while dimmed wins over the old saved brightness.
            if panel['value'] == self.last_set:
                self.set_value(serial, panel, self.saved)
            self.saved = None

    def auto(self, target):
        if not math.isfinite(target) or not 0 <= target <= 1:
            raise ValueError('Auto brightness target must be between zero and one')
        if not self.settings.get_boolean('ambient-enabled') or self.saved is not None:
            return
        serial, panel = self.panel()
        self.set_value(serial, panel, panel['min'] + target * (panel['max'] - panel['min']))

    def changed(self, _proxy, changed, _invalidated):
        if 'Backlight' not in changed.unpack():
            return
        try:
            _serial, panel = self.panel()
            current = panel['value']
            if current != self.last_seen and current != self.last_set:
                self.saved = None
                self.bus.emit_signal(None, PATH, NAME, 'BrightnessChanged', None)
            self.last_seen = current
        except (GLib.Error, ValueError):
            pass

    def property(self, _connection, _sender, _path, _interface, name):
        if name == 'HasBrightnessControl':
            try:
                self.panel()
                available = True
            except (GLib.Error, ValueError):
                available = False
            return GLib.Variant('b', available)

    def method(self, _connection, _sender, _path, _interface, method, args, invocation):
        try:
            if method == 'SetDimming':
                self.dim(args.unpack()[0])
            elif method == 'SetAutoBrightnessTarget':
                self.auto(args.unpack()[0])
            else:
                invocation.return_dbus_error('org.freedesktop.DBus.Error.UnknownMethod', method)
                return
            invocation.return_value(GLib.Variant('()', ()))
        except (GLib.Error, ValueError) as error:
            invocation.return_dbus_error(NAME + '.Error', str(error))


if __name__ == '__main__':
    bridge = Bridge()
    GLib.MainLoop().run()
