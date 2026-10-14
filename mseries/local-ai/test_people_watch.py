#!/usr/bin/python3
"""people-watch: first run records a baseline, later pushes/releases show up, --ack accepts them."""
import importlib.util
import json
import tempfile
import time
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('people_watch', HERE / 'people-watch.py')
pw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pw)


class PeopleWatch(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        root = Path(self.dir.name)
        pw.CACHE, pw.BASELINE, pw.LIST = root / 'cache.json', root / 'baseline.json', root / 'list.json'
        pw.LIST.write_text(json.dumps([{'repo': 'a/b', 'who': 'Someone', 'why': 'because'}]))
        self.pushed, self.tag = '2026-10-01T00:00:00Z', 'v1'
        pw.get = self.fake_get
        pw.REFRESH = 0

    def tearDown(self):
        self.dir.cleanup()

    def fake_get(self, path):
        if path.endswith('/releases/latest'):
            return {'tag_name': self.tag}
        if '/commits' in path:
            return [{'commit': {'message': 'new thing\n\nbody'}}]
        return {'pushed_at': self.pushed}

    def run_main(self, *argv):
        pw.sys.argv = ['people-watch'] + list(argv)
        return pw.main()

    def test_baseline_then_change_then_ack(self):
        self.assertEqual(self.run_main(), 1)          # first run: baseline only
        self.assertEqual(self.run_main(), 1)          # nothing changed
        self.tag = 'v2'
        time.sleep(0.01)
        self.assertEqual(self.run_main(), 0)          # new release
        self.run_main('--ack')
        self.assertEqual(self.run_main(), 1)          # acknowledged
        self.pushed = '2026-10-02T00:00:00Z'
        self.assertEqual(self.run_main(), 0)          # new push


if __name__ == '__main__':
    unittest.main()
