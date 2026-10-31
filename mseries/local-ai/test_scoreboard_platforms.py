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
            for index, overrides in enumerate([{}, {'hardware': 'Apple M4'}, {'model': 'example/model@revision2'}, {'mlx_version': 'new'}, {'status': 'partial'}]):
                (root / f'2026-10-30-macos-scoreboard-{index}.json').write_text(json.dumps({**base, **overrides}))
            with patch.object(scoreboard, 'RECEIPTS', root):
                rows = scoreboard.mac_rows()
            self.assertEqual(len(rows), 4)
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

    def test_text_match_requires_the_same_prompt_and_model(self):
        mac = {'_model': 'qwen2b', 'tokens': 32, 'model_reference': 'example@abc',
               'prompt_sha256': 'prompt', 'weights_sha256': 'weights', '_text_hashes': {'same'}}
        linux = {'_model': 'qwen2b', 'tokens': 32, 'model_reference': 'example@abc',
                 'prompt_sha256': 'prompt', 'weights_sha256': 'weights', '_text_hashes': {'same'}, '_arm': 'mlx-120k', '_conc': 1}
        scoreboard.annotate_cross_platform([mac], [linux, {**linux, 'prompt_sha256': 'other'},
                                                    {**linux, 'model_reference': 'example@other'}])
        self.assertEqual(mac['same_output'], 'text hash matches 1/1 Linux MLX rows')
        scoreboard.annotate_cross_platform([mac], [{**linux, '_text_hashes': {'different'}}])
        self.assertEqual(mac['same_output'], 'text hash matches 0/1 Linux MLX rows')
        scoreboard.annotate_cross_platform([mac], [{**linux, 'prompt_sha256': 'other'}])
        self.assertEqual(mac['same_output'], 'no comparable Linux text hash')
        scoreboard.annotate_cross_platform([mac], [{**linux, 'weights_sha256': 'different weights'}])
        self.assertEqual(mac['same_output'], 'no comparable Linux text hash')

    def test_chart_separates_model_revisions_and_escapes_labels(self):
        row = {'_model': 'qwen2b', '_arm': 'mac-mlx', '_conc': 1, 'model': 'model & test',
               'model_reference': 'example@abcd1234', 'tokens': 32, 'chip': 'M1 Pro', 'os': 'macOS',
               'ttft_s': 0.2, 'decode_tok_s': 25, 'driver': 'Apple Metal', 'settings': 'test', 'runs': 3, 'kernel': 'Darwin'}
        output = scoreboard.chart([row, {**row, 'chip': 'M4', 'model_reference': 'example@different'}])
        ET.fromstring(output)
        self.assertIn('model &amp; test', output)
        self.assertIn('abcd1234', output)
        self.assertIn('differen', output)
        self.assertIn('M4 · macOS', output)

    def test_relative_ratios_require_matching_workload_and_valid_measurements(self):
        base = {'_model': 'qwen2b', 'model': 'Qwen', 'tokens': 32, 'chip': 'M1 Pro',
                'model_reference': 'model@rev', 'weights_sha256': 'weights', 'prompt_sha256': 'prompt',
                '_text_hashes': {'same'}, '_conc': 1, 'runs': 3, 'decode_tok_s': 100,
                'ttft_s': 1, 'source': 'receipt', 'kernel': 'kernel', 'driver': 'driver',
                'settings': 'settings', 'os': 'macOS'}
        linux = {**base, '_arm': 'mlx-120k', 'os': 'Aurora Linux', 'decode_tok_s': 50, 'ttft_s': 3}
        result = scoreboard.relative_rows([base], [linux])
        self.assertEqual((result[0]['decode_ratio'], result[0]['ttft_ratio'], result[0]['text']), (2, 3, 'match'))
        self.assertEqual(scoreboard.relative_rows([base], [{**linux, '_text_hashes': {'other'}}])[0]['text'], 'different')
        for change in ({'chip': 'M4'}, {'model_reference': 'model@other'}, {'weights_sha256': 'other'},
                       {'prompt_sha256': 'other'}, {'runs': 2}, {'_arm': 'tensorfold'},
                       {'decode_tok_s': float('nan')}, {'ttft_s': -1}, {'_conc': 2}):
            with self.subTest(change=change):
                self.assertEqual(scoreboard.relative_rows([base], [{**linux, **change}]), [])
        ET.fromstring(scoreboard.relative_chart(result))

    def test_batch_counters_exclude_stopped_runs_and_preserve_partial_status(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = {'exit': 0, 'budget': 5000, 'result': {'tokens': [1, 2], 'generation_tps': 10,
                   'counter_delta': {'vk_submissions': 100, 'vk_compute_dispatches': 200, 'barriers_emitted': 300}},
                   'samples': []}
            receipt = {'status': 'interrupted', 'runs': [run, {**run, 'stopped': True}]}
            (root / '2026-10-27-batch-work-test.json').write_text(json.dumps(receipt))
            with patch.object(scoreboard, 'RECEIPTS', root), patch.object(scoreboard, 'HERE', root):
                rows = scoreboard.batch_counter_rows()
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['status'], rows[0]['runs'], rows[0]['submissions']), ('interrupted', 1, 100))
            self.assertEqual(rows[0]['ids'], 'only one run')
            self.assertIsNone(rows[0]['max_temp_c'])

    def test_installed_tensorfold_receipt_is_preserved(self):
        rows = scoreboard.measured_rows()
        matches = [r for r in rows if r['_arm'] == 'tensorfold' and 'b3ab9ba' in r['engine']]
        self.assertEqual({r['tokens'] for r in matches}, {32, 256})
        self.assertTrue(any('diverges after 880' in r['same_output'] for r in matches))
        self.assertTrue(all('/2026-10-30-tensorfold-b3ab9ba/' in r['source'] for r in matches))


if __name__ == '__main__':
    unittest.main()
