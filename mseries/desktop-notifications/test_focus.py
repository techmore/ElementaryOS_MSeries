# SPDX-License-Identifier: GPL-3.0-or-later
import unittest
from unittest.mock import Mock, patch

from focus import CLIENT, focus_existing, trusted_target


class FocusTests(unittest.TestCase):
    def test_focus_hint_requires_actual_backend_owner(self):
        bus = Mock()
        bus.get_name_owner.return_value = ':1.backend'
        self.assertEqual(trusted_target(bus, ':1.backend', {'desktop-entry': CLIENT}), CLIENT)
        self.assertIsNone(trusted_target(bus, ':1.other', {'desktop-entry': CLIENT}))
        self.assertIsNone(trusted_target(bus, ':1.backend', {'desktop-entry': 'other.app'}))

    def test_only_exact_single_matching_existing_window_is_focused(self):
        bus, interface = Mock(), Mock()
        with patch('focus.dbus.Interface', return_value=interface):
            focus_existing(bus, CLIENT)
        callback = interface.GetWindows.call_args.kwargs['reply_handler']
        callback([(4, {'app-id': 'other.app'}), (7, {'app-id': CLIENT})])
        self.assertEqual(interface.FocusWindow.call_args.args, (7,))
        interface.FocusWindow.reset_mock()
        callback([(7, {'app-id': CLIENT}), (8, {'app-id': CLIENT})])
        interface.FocusWindow.assert_not_called()

    def test_foreign_target_does_not_contact_compositor(self):
        bus = Mock()
        focus_existing(bus, 'other.app')
        bus.get_object.assert_not_called()


if __name__ == '__main__':
    unittest.main()
