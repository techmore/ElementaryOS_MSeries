#!/usr/bin/env python3
"""Offline tests for fetch-kernel.py and kernel-pin.json (no network)."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

here = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('fetch_kernel', here / 'fetch-kernel.py')
fk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fk)


class PinTests(unittest.TestCase):
    def test_pin_is_immutable_and_complete(self):
        pin, items = fk.load_pin()
        self.assertTrue(pin['release_tag'].startswith('kernel-'))
        self.assertEqual(len(items), 4)

    def test_pin_matches_fairydust_profile(self):
        pin, _ = fk.load_pin()
        fk.check_profiles(pin)

    def test_mutable_tag_is_refused(self):
        pin = json.loads(fk.PIN.read_text())
        pin['release_tag'] = 'main'
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'pin.json'
            p.write_text(json.dumps(pin))
            with self.assertRaises(SystemExit):
                fk.load_pin(p)

    def _serve(self, d, pin, items, corrupt=None):
        rel = Path(d) / 'rel'
        rel.mkdir()
        for it in items:
            data = b'bad' if it['asset'] == corrupt else it['asset'].encode()
            (rel / it['asset']).write_bytes(data)
            it['sha256'] = fk.sha256(it['asset'].encode())
        return 'file://' + str(rel) + '/{asset}'

    def test_fetch_verifies_and_writes_sums(self):
        pin, items = fk.load_pin()
        with tempfile.TemporaryDirectory() as d:
            base = self._serve(d, pin, items)
            out = Path(d) / 'out'
            fk.fetch(pin, items, out, base)
            sums = (out / 'SHA256SUMS').read_text().splitlines()
            self.assertEqual(len(sums), 3)
            self.assertIn('m1n1_1.5.2-2ubuntu0.1~asahi1_arm64.deb', (out / 'UPSTREAM-SHA256SUMS').read_text())

    def test_checksum_mismatch_fails(self):
        pin, items = fk.load_pin()
        with tempfile.TemporaryDirectory() as d:
            base = self._serve(d, pin, items, corrupt=items[1]['asset'])
            with self.assertRaises(SystemExit):
                fk.fetch(pin, items, Path(d) / 'out', base)


if __name__ == '__main__':
    unittest.main()
