# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure fixtures only: no accessibility bus, app inspection or display access."""
import unittest
from unittest.mock import patch
import subprocess
from model import positions
from workarea import ShellCache, shell_workarea, dock_workarea, matching_height, probe_child


class WorkareaTests(unittest.TestCase):
    def test_bottom_dock_only_limits_capacity_edge(self):
        area = (0, 0, 2419, 1571)
        reduced = dock_workarea(area, area, 72)
        self.assertEqual(reduced, (0, 0, 2419, 1499))
        self.assertEqual(positions(area, 1)[0][1] - positions(reduced, 1)[0][1], 0)

    def test_top_panel_124_places_first_popup_at_140(self):
        full = (0, 0, 2419, 1571)
        reduced = shell_workarea(full, full, 124, 72)
        self.assertEqual(reduced, (0, 124, 2419, 1375))
        self.assertEqual(positions(reduced, 3)[0], (2043, 140, 360, 72))
        self.assertEqual(positions(full, 3)[0][1], 16)
        self.assertEqual(positions(reduced, 3)[1][1], 224)

    def test_top_panel_reservation_is_not_doubled(self):
        full = (0, 0, 2419, 1571)
        reserved = (0, 124, 2419, 1375)
        self.assertEqual(shell_workarea(reserved, full, 124, 72), reserved)
        self.assertEqual(shell_workarea((0, 24, 2419, 1547), full, 124, 72), reserved)
        self.assertEqual(matching_height({'app': 'io.elementary.wingpanel', 'showing': True,
                                         'width': 2419, 'height': 124}, 2419), 124)

    def test_reservation_not_double_subtracted(self):
        full = (0, 0, 2419, 1571)
        self.assertEqual(dock_workarea((0, 28, 2419, 1471), full, 72),
                         (0, 28, 2419, 1471))
        self.assertEqual(dock_workarea((0, 28, 2419, 1511), full, 72),
                         (0, 28, 2419, 1471))
        self.assertEqual(dock_workarea((0, 0, 2419, 1471), full, 72),
                         (0, 0, 2419, 1471))

    def test_absent_or_unrelated_dock_is_unchanged(self):
        full = (0, 0, 1280, 800)
        for frame in ({}, {'app': 'message-app', 'showing': True, 'width': 1280, 'height': 72},
                      {'app': 'io.elementary.dock', 'showing': False, 'width': 1280, 'height': 72},
                      {'app': 'io.elementary.dock', 'showing': True, 'width': 2419, 'height': 72}):
            self.assertEqual(dock_workarea(full, full, matching_height(frame, 1280)), full)

    def test_bogus_y_zero_dock_is_known_bottom_not_top(self):
        frame = {'app': 'io.elementary.dock', 'showing': True, 'x': 0, 'y': 0,
                 'width': 2419, 'height': 72}
        height = matching_height(frame, 2419)
        self.assertEqual(height, 72)
        self.assertEqual(dock_workarea((0, 0, 2419, 1571), (0, 0, 2419, 1571), height)[1], 0)

    def test_inset_clipped_and_negative_origin_supported(self):
        full = (-1280, -100, 1280, 800)
        self.assertEqual(dock_workarea(full, full, -72), full)
        self.assertEqual(dock_workarea(full, full, 10000), (-1280, -100, 1280, 544))
        self.assertGreater(dock_workarea((0, 0, 100, 20), (0, 0, 100, 20), 256)[3], 0)

    def test_async_cache_fallback_bounded_refresh_and_absence(self):
        jobs, posts, changed = [], [], []
        now = [0]
        cache = ShellCache(posts.append, lambda: changed.append(True), fallback=(124, 72),
                          probe=lambda width: (140, 96), clock=lambda: now[0], start=jobs.append)
        for _ in range(50):
            self.assertEqual(cache.current((0, 0, 1280, 800)), (124, 72))
        self.assertEqual(len(jobs), 1)
        jobs.pop()()
        self.assertEqual(cache.insets, (124, 72))  # Completion only runs on main loop.
        posts.pop()()
        self.assertEqual(cache.current((0, 0, 1280, 800)), (140, 96))
        self.assertEqual(changed, [True])
        self.assertEqual(jobs, [])
        now[0] = 16
        cache.probe = lambda width: (0, 0)
        cache.current((0, 0, 1280, 800))
        jobs.pop()(); posts.pop()()
        self.assertEqual(cache.insets, (0, 0))
        now[0] = 32
        cache.probe = lambda width: None
        cache.current((0, 0, 1280, 800))
        jobs.pop()(); posts.pop()()
        self.assertEqual(cache.insets, (124, 72))

    def test_monitor_change_rejects_stale_result(self):
        jobs, posts = [], []
        cache = ShellCache(posts.append, lambda: None, fallback=(124, 72),
                          probe=lambda width: (140, 96), start=jobs.append)
        cache.current((0, 0, 1280, 800))
        cache.current((1280, 0, 1920, 1080))
        self.assertEqual(len(jobs), 1)
        jobs.pop()(); posts.pop()()
        self.assertEqual(cache.insets, (124, 72))
        cache.current((1280, 0, 1920, 1080))
        self.assertEqual(len(jobs), 1)

    def test_monitor_event_invalidates_even_unchanged_geometry(self):
        jobs, posts = [], []
        cache = ShellCache(posts.append, lambda: None, fallback=(124, 72),
                          probe=lambda width: (140, 96), start=jobs.append)
        cache.current((0, 0, 1280, 800))
        cache.invalidate()
        cache.current((0, 0, 1280, 800))
        jobs.pop()(); posts.pop()()
        self.assertEqual(cache.insets, (124, 72))
        cache.current((0, 0, 1280, 800))
        self.assertEqual(len(jobs), 1)

    def test_per_edge_unavailable_preserves_only_that_fallback(self):
        jobs, posts = [], []
        cache = ShellCache(posts.append, lambda: None, fallback=(124, 72),
                           probe=lambda width: (None, 96), start=jobs.append)
        cache.current((0, 0, 2419, 1571))
        jobs.pop()(); posts.pop()()
        self.assertEqual(cache.insets, (124, 96))

    def test_no_environment_fallback_in_plain_fixture(self):
        with patch.dict('os.environ', {}, clear=True):
            cache = ShellCache(lambda cb: None, lambda: None, start=lambda cb: None)
            self.assertEqual(cache.current((0, 0, 1280, 800)), (0, 0))

    def test_child_probe_has_hard_timeout_and_ignores_invalid_result(self):
        with patch('workarea.subprocess.run', side_effect=subprocess.TimeoutExpired('probe', 0.8)) as run:
            self.assertIsNone(probe_child(2419))
            self.assertEqual(run.call_args.kwargs['timeout'], 0.8)
            self.assertNotIn('shell', run.call_args.kwargs)


if __name__ == '__main__':
    unittest.main()
