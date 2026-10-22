# SPDX-License-Identifier: GPL-3.0-or-later
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from center import Center, message_handle
from history import History


class HistoryTests(unittest.TestCase):
    def test_retention_bounds_and_replacement_read_state(self):
        history = History(limit=3, clock=lambda: 123)
        for nid in range(10):
            history.add(nid, 'App', 'Title', 'x' * 5000, ['reply', 'Reply'])
        self.assertEqual(list(history.entries), [7, 8, 9])
        self.assertEqual(len(history.entries[9]['body']), 1024)
        history.read(9)
        history.add(9, 'App', 'Title', 'x' * 5000, ['reply', 'Reply'])
        self.assertTrue(history.entries[9]['read'])
        history.add(9, 'App', 'Title', 'New message', ['reply', 'Reply'])
        self.assertFalse(history.entries[9]['read'])
        self.assertEqual(history.mark_all_read(), 3)
        self.assertEqual(history.unread, 0)

    def test_expired_message_keeps_trusted_reply_but_not_raw_handle_in_public_rows(self):
        history = History()
        history.add(1, 'App', 'Sender', 'Preview', ['reply', 'Reply'], handle='message123')
        history.add(2, 'Other', 'Title', 'Body', ['reply', 'Reply'])
        rows = history.list(100, {})
        self.assertFalse(rows[0]['can_reply'])
        self.assertTrue(rows[1]['can_reply'])
        self.assertNotIn('handle', rows[1])

    def test_hint_is_data_not_a_command(self):
        hint = {'omarchy-exec-argv': json.dumps(['/evil', '-m', 'blueferry.client_activation',
                                               '--message=message123'])}
        self.assertEqual(message_handle(hint, True), 'message123')
        self.assertEqual(message_handle(hint, False), '')
        hint['omarchy-exec-argv'] = json.dumps(['/bin/sh', '-c', 'danger'])
        self.assertEqual(message_handle(hint, True), '')


class CenterTests(unittest.TestCase):
    def center(self):
        center = Center.__new__(Center)
        center.history = History()
        center.server = SimpleNamespace(store=SimpleNamespace(items={}, clear=Mock(), activate=Mock()))
        center.view = SimpleNamespace(muted=lambda: False, settings=Mock())
        center.Changed, center._focus_later = Mock(), Mock()
        return center

    def test_mark_all_read_is_local_and_clears_toasts_without_phone_api(self):
        center = self.center()
        center.history.add(1, 'App', 'Sender', 'Preview', [])
        self.assertEqual(center.MarkAllRead(), 1)
        center.server.store.clear.assert_called_once_with()
        self.assertEqual(center.history.unread, 0)

    def test_expired_real_message_uses_fixed_helper_and_validated_handle(self):
        center = self.center()
        center.history.add(1, 'App', 'Sender', 'Preview', ['reply', 'Reply'], handle='message123')
        with patch('center.subprocess.Popen') as launch:
            self.assertTrue(center.InvokeAction(1, 'reply'))
        self.assertEqual(launch.call_args.args[0], ['/usr/bin/python3', '-m',
                         'blueferry.client_activation', '--message=message123'])
        self.assertNotIn('shell', launch.call_args.kwargs)
        self.assertEqual(center.history.unread, 0)

    def test_live_action_uses_original_action_signal_and_unknown_action_is_inert(self):
        center = self.center()
        center.history.add(1, 'App', 'Sender', 'Preview', ['reply', 'Reply'])
        center.server.store.items[1] = object()
        self.assertTrue(center.InvokeAction(1, 'reply'))
        center.server.store.activate.assert_called_once_with(1, 'reply')
        self.assertFalse(center.InvokeAction(1, 'send'))


if __name__ == '__main__':
    unittest.main()
