#!/usr/bin/env python3
"""Offline regression tests: never start a workload or access the owner's devices."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import macos_profile as mac
import linux_profile as linux
import parity


class ParityTests(unittest.TestCase):
    def test_missing_top_process_is_unknown(self):
        self.assertIsNone(parity.resolve({'scenarios': {'idle_minimal': {'top_processes': []}}},
                                         'p:idle_minimal:gala:cpu_ms_per_s'))

    def test_missing_decoder_is_unknown(self):
        summary = {'scenarios': {'video_local': {'playback': {'error': 'socket closed'}}}}
        self.assertIsNone(parity.resolve(summary, 'v:video_local.hwdec-current'))
        summary['scenarios']['video_local']['playback']['hwdec-current'] = 'no'
        self.assertEqual(parity.resolve(summary, 'v:video_local.hwdec-current'), 0)

    def test_scoring_boundaries_and_stale_ratio(self):
        item = {'mac_value': 10, 'linux': {'value': 11}, 'dir': 'lower'}
        self.assertEqual(parity.score(item), 'pass')
        item['linux']['value'] = 15
        self.assertEqual(parity.score(item), 'close')
        item['linux']['value'] = 16
        self.assertEqual(parity.score(item), 'gap')
        for value in (None, True, float('nan'), float('inf')):
            item['linux']['value'] = value
            self.assertEqual(parity.score(item), 'awaiting-linux')
            self.assertNotIn('ratio', item)

    def test_zero_dropped_frames(self):
        item = {'mac_value': 0, 'linux': {'value': 0}, 'dir': 'lower'}
        self.assertEqual(parity.score(item), 'pass')
        item['linux']['value'] = 1
        self.assertEqual(parity.score(item), 'gap')

    def test_partial_import_clears_stale_values(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data, md, run = root/'parity.json', root/'PARITY.md', root/'summary.json'
            doc = json.loads(parity.DATA.read_text())
            item = next(i for c in doc['categories'] for i in c['items'] if i['id'] == 'W1')
            item['linux']['value'] = 1
            item['checked'] = True
            data.write_text(json.dumps(doc))
            run.write_text(json.dumps({'inventory': {}, 'scenarios': {}}))
            with patch.object(parity, 'DATA', data), patch.object(parity, 'MD', md), \
                 patch.object(sys, 'argv', ['parity.py', '--linux-run', str(run)]):
                parity.main()
            item = next(i for c in json.loads(data.read_text())['categories'] for i in c['items'] if i['id'] == 'W1')
            self.assertIsNone(item['linux']['value'])
            self.assertNotIn('checked', item)
            self.assertIn('not measured', item['linux']['text'])

    def test_invalid_cli_does_not_modify_data(self):
        for args in (['--linux', 'W1=nan'], ['--linux', 'TYPO=3'], ['--check', 'W1'],
                     ['--linux', 'malformed'], ['--kind', 'W1=guess']):
            with self.subTest(args=args), tempfile.TemporaryDirectory() as directory:
                data = Path(directory)/'parity.json'
                original = parity.DATA.read_bytes()
                data.write_bytes(original)
                with patch.object(parity, 'DATA', data), patch.object(sys, 'argv', ['parity.py', *args]):
                    with self.assertRaises(SystemExit):
                        parity.main()
                self.assertEqual(data.read_bytes(), original)


class MeasurementTests(unittest.TestCase):
    def test_statistics_ignore_invalid_samples(self):
        self.assertEqual(mac.stats([None, True, float('nan'), float('inf'), 0, 10]),
                         {'median': 5.0, 'p10': 1.0, 'p90': 9.0, 'n': 2})

    def test_charge_is_not_energy(self):
        with tempfile.TemporaryDirectory() as directory:
            battery = Path(directory)
            (battery/'charge_now').write_text('4000000')
            (battery/'current_now').write_text('-1000000')
            (battery/'voltage_now').write_text('12000000')
            (battery/'status').write_text('Discharging')
            with patch.object(linux, 'BAT', battery), patch.object(linux, 'SYS_POWER', None):
                power = linux.read_power()
            self.assertEqual(power['battery_flow_w'], 12)
            self.assertIsNone(power['energy_uwh'])

    def test_proc_busy_does_not_double_count_guests(self):
        with patch.object(linux, 'rd', return_value='cpu 100 20 30 400 50 6 7 8 90 10\n'):
            self.assertEqual(linux.proc_stat(), 171)
        with patch.object(linux, 'rd', return_value=None):
            self.assertEqual(linux.proc_stat(), 0)

    def test_burst_without_cpu_rail_is_not_zero_ramp(self):
        self.assertIsNone(mac.burst_analysis([{'cpu_w': None}], {'burst_offset_s': 0}))

    def test_video_override_must_exist(self):
        self.assertIsNone(mac.video_file({'video': 'test-1080p-h264.mp4'},
                                        SimpleNamespace(video='/no/such/file', video_dir='/tmp')))

    def test_invalid_run_options_rejected(self):
        for scale, settle, only in ((0, 0, None), (-1, 0, None), (float('nan'), 0, None),
                                   (1, -1, None), (1, 0, 'unknown')):
            with self.subTest(scale=scale, settle=settle, only=only), self.assertRaises(SystemExit):
                mac.validate_run_args(argparse.ArgumentParser(), SimpleNamespace(scale=scale, settle=settle, only=only))

    def test_linux_interrupt_restores_display(self):
        args = SimpleNamespace(video=None, video_dir='/tmp', browser='xdg-open', yes=True,
                               settle=0, scale=1, allow_blank=True)
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(linux, 'blank') as blank, patch.object(linux.time, 'sleep', side_effect=[None, None, KeyboardInterrupt]), \
             patch.object(linux, 'PowerSampler') as sampler, patch.object(linux, 'snapshot', return_value={}), \
             patch.object(linux, 'per_process', return_value={}):
            with self.assertRaises(KeyboardInterrupt):
                linux.run_scenario('idle_screen_off', mac.SCENARIOS['idle_screen_off'], Path(directory), {}, args)
            self.assertEqual([call.args for call in blank.call_args_list], [(False,), (True,)])
            sampler.return_value.stop.assert_called_once()

    def test_macos_start_failure_restores_display(self):
        args = SimpleNamespace(video=None, video_dir='/tmp', yes=True, settle=0, scale=1)
        with tempfile.TemporaryDirectory() as directory, patch.object(mac.time, 'sleep'), \
             patch.object(mac, 'display_off'), patch.object(mac, 'display_on') as wake, \
             patch.object(mac, 'BatterySampler') as sampler, \
             patch.object(mac, 'start_powermetrics', side_effect=OSError('missing executable')):
            with self.assertRaises(OSError):
                mac.run_scenario('idle_screen_off', mac.SCENARIOS['idle_screen_off'], Path(directory), [], args)
            wake.assert_called_once()
            sampler.return_value.stop.assert_called_once()

    def test_quicktime_closes_only_owned_document(self):
        with patch.object(mac, 'run', return_value='true\n') as run:
            ident = mac.video_local('/tmp/test.mp4')
            mac.video_stop(ident)
            self.assertIn('set looping of clip to true', run.call_args_list[0].args[0][-1])
            self.assertIn('close clip saving no', run.call_args_list[1].args[0][-1])
            self.assertIn('POSIX file ' + json.dumps(str(Path('/tmp/test.mp4').resolve())), run.call_args_list[1].args[0][-1])
            self.assertNotIn('every document', run.call_args_list[1].args[0][-1])

    def test_scaled_cpu_burst_has_recovery_window(self):
        args = SimpleNamespace(video=None, video_dir='/tmp', yes=True, settle=0, scale=.01)
        proc = Mock(returncode=0, stderr=None)
        proc.poll.return_value = 0
        with tempfile.TemporaryDirectory() as directory, patch.object(mac.time, 'sleep'), \
             patch.object(mac, 'BatterySampler', return_value=Mock(samples=[])), patch.object(mac.mp, 'Process'), \
             patch.object(mac, 'summarize_scenario', return_value={}), \
             patch.object(mac, 'start_powermetrics', return_value=proc) as start:
            mac.run_scenario('cpu_burst', mac.SCENARIOS['cpu_burst'], Path(directory), [], args)
            self.assertGreaterEqual(start.call_args.args[2], 300)


if __name__ == '__main__':
    unittest.main()
