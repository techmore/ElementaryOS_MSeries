"""Regression checks for provenance-preserving platform scoreboard ingestion."""
import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import scoreboard


class PlatformScoreboardTest(unittest.TestCase):
    def test_macs_do_not_overwrite_other_chips_or_revisions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = {'status': 'complete', 'concurrency': 1, 'model_key': 'qwen2b',
                    'model': 'example/model@revision1', 'max_tokens': 32,
                    'hardware': 'Apple M1 Pro', 'os': 'macOS 27.2', 'kernel': 'Darwin',
                    'runs': [{'arm': 'mac-mlx', 'decode_tps': n, 'ttft_s': 0.2, 'total_s': 0.6} for n in (10, 20, 30)]}
            for index, overrides in enumerate([{}, {'hardware': 'Apple M4'}, {'model': 'example/model@revision2'}, {'status': 'partial'}]):
                (root / f'2026-10-30-macos-scoreboard-{index}.json').write_text(json.dumps({**base, **overrides}))
            with patch.object(scoreboard, 'RECEIPTS', root):
                rows = scoreboard.mac_rows()
            self.assertEqual(len(rows), 3)
            self.assertEqual({x['model_reference'] for x in rows}, {'example/model@revision1', 'example/model@revision2'})
            self.assertIn('M4', {x['chip'] for x in rows})
            self.assertTrue(all(x['decode_tok_s'] == 20 for x in rows))
            self.assertTrue(all(x['gate'] == 'not gated' for x in rows))

    def test_linux_chip_and_kernel_are_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            receipt = {'status': 'complete', 'model_key': 'qwen2b', 'model': 'example/model@abc',
                       'max_tokens': 32, 'concurrency': 1, 'driver': 'test driver', 'os': 'Aurora Linux',
                       'arms': ['mlx-120k'], 'runs': [{'arm': 'mlx-120k', 'text': 'synthetic',
                           'text_sha256': 'x', 'decode_tps': 42, 'ttft_s': .2, 'total_s': 1}]}
            for index, chip in enumerate(['M1 Pro', 'M4']):
                (root / f'2026-11-01-engine-compare-test-{index}.json').write_text(json.dumps({**receipt, 'chip': chip, 'kernel': 'Aurora test'}))
            with patch.object(scoreboard, 'RECEIPTS', root), patch.object(scoreboard, 'HERE', root), patch.object(scoreboard, 'gate_results', return_value={}):
                rows = scoreboard.measured_rows()
            self.assertEqual({row['chip'] for row in rows}, {'M1 Pro', 'M4'})
            self.assertTrue(all(row['os'] == 'Aurora Linux' for row in rows))

    def test_chart_separates_model_revisions_and_escapes_labels(self):
        row = {'_model': 'qwen2b', '_arm': 'mac-mlx', '_conc': 1, 'model': 'model & test',
               'model_reference': 'example@abcd1234', 'tokens': 32, 'chip': 'M1 Pro', 'os': 'macOS',
               'ttft_s': 0.2, 'decode_tok_s': 25, 'driver': 'Apple Metal', 'runs': 3, 'kernel': 'Darwin'}
        output = scoreboard.chart([row, {**row, 'chip': 'M4', 'model_reference': 'example@different'}])
        ET.fromstring(output)
        self.assertIn('model &amp; test', output)
        self.assertIn('abcd1234', output)
        self.assertIn('differen', output)
        self.assertIn('M4 · macOS', output)

    def test_installed_tensorfold_receipt_is_preserved(self):
        rows = scoreboard.measured_rows()
        matches = [r for r in rows if r['_arm'] == 'tensorfold' and 'b3ab9ba' in r['engine']]
        self.assertEqual({r['tokens'] for r in matches}, {32, 256})
        self.assertTrue(any('diverges after 880' in r['same_output'] for r in matches))
        self.assertTrue(all('/2026-10-30-tensorfold-b3ab9ba/' in r['source'] for r in matches))


if __name__ == '__main__':
    unittest.main()
