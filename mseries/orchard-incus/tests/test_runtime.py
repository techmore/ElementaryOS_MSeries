"""Concurrency regressions: stalled reads and unlimited guest output."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchard_incus.runtime import LatestRead, OutputMailbox


class Reads(unittest.TestCase):
    def setUp(self):
        self.running, self.results, self.errors = [], [], []
        self.task = LatestRead(lambda fn, done: self.running.append((fn, done)))

    def submit(self, value):
        self.task.submit(lambda: value, self.results.append, self.errors.append)

    def finish(self, error=None):
        fn, done = self.running.pop(0)
        done(fn(), error)

    def test_navigation_keeps_one_running_and_only_latest_pending(self):
        for value in range(1000):
            self.submit(value)
        self.assertEqual(len(self.running), 1)
        self.finish()
        self.assertEqual(self.results, [])
        self.assertEqual(len(self.running), 1)
        self.finish()
        self.assertEqual(self.results, [999])
        self.assertFalse(self.task.running)

    def test_navigation_away_discards_results_and_errors(self):
        self.submit('old')
        self.task.invalidate()
        self.finish(RuntimeError('stale failure'))
        self.assertEqual(self.errors, [])
        self.assertEqual(self.results, [])

    def test_current_failure_delivered_and_can_retry(self):
        self.submit('failed')
        self.finish(RuntimeError('offline'))
        self.assertEqual(str(self.errors[0]), 'offline')
        self.submit('recovered')
        self.finish()
        self.assertEqual(self.results, ['recovered'])


class Output(unittest.TestCase):
    def test_flood_is_bounded_and_uses_one_delivery(self):
        calls = []
        box = OutputMailbox(lambda: calls.append(True), limit=1024)
        for _ in range(100000):
            box.put('0123456789\n')
        self.assertEqual(len(calls), 1)
        self.assertEqual(box.size, 1024)
        text = box.take()
        self.assertIn('Skipped 1,098,976 characters', text)
        self.assertTrue(text.endswith('0123456789\n'))
        self.assertEqual(box.take(), '')
        box.put('next')
        self.assertEqual(len(calls), 2)
        self.assertEqual(box.take(), 'next')

    def test_parallel_producers_do_not_lose_wakeup(self):
        calls = []
        box = OutputMailbox(lambda: calls.append(True), limit=100000)
        def put(_):
            for _ in range(1000):
                box.put('λ')
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(put, range(4)))
        self.assertEqual(calls, [True])
        self.assertEqual(box.take(), 'λ' * 4000)
