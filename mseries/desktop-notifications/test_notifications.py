# SPDX-License-Identifier: GPL-3.0-or-later
"""No test in this module owns a bus or initializes a display."""
import unittest
from unittest.mock import Mock, patch
from model import Store, positions


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.tasks = {}
        self.closed, self.invoked = [], []
        self.serial = 0
        self.muted = False
        def schedule(delay, callback):
            self.serial += 1
            self.tasks[self.serial] = (delay, callback)
            return self.serial
        self.store = Store(schedule, lambda key: self.tasks.pop(key), lambda: None,
                           lambda *args: self.closed.append(args),
                           lambda *args: self.invoked.append(args), lambda: self.muted)

    def notify(self, **kw):
        args = dict(owner=':1.42', replaces=0, app='Fixture', summary='Hello',
                    body='Message', actions=['default', 'Open', 'reply', 'Reply'], timeout=-1)
        args.update(kw)
        return self.store.notify(**args)

    def test_actions_are_exact_and_never_dispatch_unknown(self):
        for key in ('default', 'reply', 'custom:key'):
            nid = self.notify(actions=['default', 'Open', 'reply', 'Reply', 'custom:key', 'Custom'])
            self.store.activate(nid, 'forged')
            self.assertIn(nid, self.store.items)
            self.store.activate(nid, key)
            self.store.activate(nid, key)
            self.assertEqual(self.invoked[-1], (nid, key))
            self.assertEqual(self.closed[-1], (nid, 4))
        self.assertEqual(len(self.invoked), 3)
        self.assertFalse(self.tasks)

    def test_bounds_eviction_timeouts_and_no_persistence(self):
        for _ in range(50):
            self.notify(body='x' * 100000, timeout=999999)
        self.assertEqual(len(self.store.items), 3)
        self.assertEqual(len(self.tasks), 3)
        self.assertTrue(all(len(n.body) == 1024 for n in self.store.items.values()))
        self.assertTrue(all(t[0] == 120000 for t in self.tasks.values()))
        self.assertEqual(self.closed[0], (1, 4))
        self.store.clear()
        self.assertFalse(self.tasks)
        self.assertFalse(self.store.items)

    def test_expiry_dismissal_and_client_close_reasons(self):
        nid = self.notify()
        timer = self.store.timers[nid]
        _, callback = self.tasks.pop(timer)
        self.assertFalse(callback())
        self.assertEqual(self.closed[-1], (nid, 1))
        for reason in (2, 3):
            nid = self.notify(timeout=0)
            self.store.close(nid, reason)
            self.assertEqual(self.closed[-1], (nid, reason))
        self.assertFalse(self.tasks)

    def test_replacement_cancels_old_expiry_and_checks_sender(self):
        nid = self.notify()
        timer = self.store.timers[nid]
        self.assertEqual(self.notify(replaces=nid, body='new', timeout=0), nid)
        self.assertNotIn(timer, self.tasks)
        foreign = self.notify(owner=':1.99', replaces=nid)
        self.assertNotEqual(foreign, nid)
        self.store.close(nid, 3, owner=':1.99')
        self.assertIn(nid, self.store.items)

    def test_dnd_drops_content_and_timers(self):
        self.muted = True
        for _ in range(50):
            self.notify()
        self.assertFalse(self.store.items)
        self.assertFalse(self.tasks)
        self.assertFalse(self.invoked)

    def test_plain_text_and_action_bounds(self):
        nid = self.notify(body='<script>bad()</script>\x00\u202e',
                          actions=['default', 'Open', 'reply', 'Reply'] +
                          [v for n in range(30) for v in (str(n), 'Long label' * 20)])
        notice = self.store.items[nid]
        self.assertEqual(notice.body, '<script>bad()</script>')
        self.assertEqual(len(notice.actions), 4)
        self.assertTrue(all(len(label) <= 48 for _, label in notice.actions))
        self.assertFalse(self.invoked)

    def test_workarea_origin_gaps_and_small_screen(self):
        slots = positions((100, 50, 1280, 720), 3)
        self.assertEqual(slots[0], (1004, 574, 360, 180))
        self.assertEqual(slots[1][1], slots[0][1] - 192)
        for area in ((0, 0, 300, 200), (-1920, 0, 1920, 1080)):
            for x, y, w, h in positions(area, 3):
                self.assertGreaterEqual(x, area[0])
                self.assertGreaterEqual(y, area[1])
                self.assertLessEqual(x + w, area[0] + area[2])
                self.assertLessEqual(y + h, area[1] + area[3])


class DispatchTests(unittest.TestCase):
    def test_dispatch_is_only_model_and_signals(self):
        from notifications import Server
        fake = Mock()
        fake.store.notify.return_value = 42
        self.assertEqual(Server.Notify(fake, 'App', 0, '/evil/image', 'Title', 'Body',
                                      ['reply', 'Reply'], {'omarchy-exec-argv': 'evil'},
                                      8000, sender=':1.42'), 42)
        fake.store.notify.assert_called_once_with(':1.42', 0, 'App', 'Title', 'Body',
                                                 ['reply', 'Reply'], 8000)
        Server.CloseNotification(fake, 42, sender=':1.42')
        fake.store.close.assert_called_once_with(42, 3, owner=':1.42')
        self.assertEqual(Server.GetCapabilities(fake), ['actions', 'body'])

    def test_bus_name_never_steals_or_queues_by_default(self):
        from notifications import request_name
        with patch('notifications.dbus.service.BusName') as name:
            request_name('fixture')
            name.assert_called_once_with('org.freedesktop.Notifications', bus='fixture',
                                         allow_replacement=False, replace_existing=False,
                                         do_not_queue=True)


if __name__ == '__main__':
    unittest.main()
