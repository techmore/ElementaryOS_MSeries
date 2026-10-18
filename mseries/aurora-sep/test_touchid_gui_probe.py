"""Exercise the real GUI probe without GTK, a bus, a sensor or PAM writes."""
from pathlib import Path
import runpy
import sys
import types
import unittest
from unittest.mock import Mock, patch


class ProbeTests(unittest.TestCase):
    def load_gui(self, manager):
        gi = types.ModuleType('gi'); gi.require_version = Mock()
        repo = types.ModuleType('gi.repository')
        repo.Gtk = types.SimpleNamespace(Window=object)
        repo.GLib = types.SimpleNamespace(Error=RuntimeError)
        repo.Gio = types.SimpleNamespace(DBusProxy=types.SimpleNamespace(new_sync=Mock(return_value=manager)),
                                         DBusProxyFlags=types.SimpleNamespace(NONE=0),
                                         DBusCallFlags=types.SimpleNamespace(NONE=0))
        with patch.dict(sys.modules, {'gi': gi, 'gi.repository': repo}):
            module = runpy.run_path(str(Path(__file__).with_name('mseries-touchid-settings')))
        return module['TouchIdWindow'], repo.Gio

    def test_first_refresh_constructs_manager_before_querying_device(self):
        manager = Mock(); manager.call_sync.return_value.unpack.return_value = ('/device/0',)
        cls, gio = self.load_gui(manager)
        win = cls.__new__(cls)
        win.manager = None; win.bus = object(); win._unit_state = lambda _: 'active'
        with patch.object(Path, 'glob', return_value=[]):
            facts = win.collect_facts()
        self.assertTrue(facts['device'])
        self.assertEqual(win.device_path, '/device/0')
        self.assertEqual(gio.DBusProxy.new_sync.call_count, 1)
        self.assertEqual(manager.call_sync.call_args.args[0], 'GetDefaultDevice')
        self.assertEqual(manager.call_sync.call_args.args[3], 3000)

    def test_probe_failure_is_diagnostic_and_does_not_write_or_restart(self):
        manager = Mock(); manager.call_sync.side_effect = RuntimeError('device busy')
        cls, _ = self.load_gui(manager)
        win = cls.__new__(cls); win.manager = manager; win._unit_state = lambda _: 'active'
        with patch.object(Path, 'glob', return_value=[]):
            facts = win.collect_facts()
        self.assertFalse(facts['device'])
        self.assertIn('busy', facts['device_error'])
        self.assertEqual(manager.method_calls[0][0], 'call_sync')


if __name__ == '__main__':
    unittest.main()
