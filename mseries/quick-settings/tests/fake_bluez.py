"""BlueZ fixture on a private test bus; never touches a real Bluetooth adapter."""
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

DBusGMainLoop(set_as_default=True)
bus = dbus.SessionBus()
owner = dbus.service.BusName('org.bluez', bus)
ADAPTER = 'org.bluez.Adapter1'
DEVICE = 'org.bluez.Device1'

class Node(dbus.service.Object):
    def __init__(self, path, interface, values):
        super().__init__(bus, path)
        self.interface, self.values, self.path = interface, values, path

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='s', out_signature='a{sv}')
    def GetAll(self, interface):
        return self.values if interface == self.interface else {}

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='ss', out_signature='v')
    def Get(self, interface, key):
        return self.values[key]

    @dbus.service.method('org.freedesktop.DBus.Properties', in_signature='ssv')
    def Set(self, interface, key, value):
        assert interface == ADAPTER and key == 'Powered'
        self.values[key] = dbus.Boolean(value)
        self.PropertiesChanged(interface, {key: self.values[key]}, [])

    @dbus.service.signal('org.freedesktop.DBus.Properties', signature='sa{sv}as')
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    @dbus.service.method(DEVICE)
    def Connect(self):
        if self.values.get('Alias') == 'Offline headset':
            raise dbus.exceptions.DBusException('Device unavailable', name='org.bluez.Error.Failed')
        self.values['Connected'] = dbus.Boolean(True)
        self.PropertiesChanged(DEVICE, {'Connected': dbus.Boolean(True)}, [])

    @dbus.service.method(DEVICE)
    def Disconnect(self):
        self.values['Connected'] = dbus.Boolean(False)
        self.PropertiesChanged(DEVICE, {'Connected': dbus.Boolean(False)}, [])

nodes = [
    Node('/org/bluez/hci0', ADAPTER, {'Powered': dbus.Boolean(True)}),
    Node('/org/bluez/hci0/dev_TEST', DEVICE, {'Alias': 'Test keyboard', 'Paired': dbus.Boolean(True), 'Connected': dbus.Boolean(False), 'Icon': 'input-keyboard-symbolic'}),
    Node('/org/bluez/hci0/dev_OFFLINE', DEVICE, {'Alias': 'Offline headset', 'Paired': dbus.Boolean(True), 'Connected': dbus.Boolean(False)}),
    Node('/org/bluez/hci0/dev_UNPAIRED', DEVICE, {'Alias': 'Stranger', 'Paired': dbus.Boolean(False), 'Connected': dbus.Boolean(False)}),
]

class Manager(dbus.service.Object):
    @dbus.service.method('org.freedesktop.DBus.ObjectManager', out_signature='a{oa{sa{sv}}}')
    def GetManagedObjects(self):
        return {node.path: {node.interface: node.values} for node in nodes}

manager = Manager(bus, '/')
print('READY', flush=True)
GLib.MainLoop().run()
