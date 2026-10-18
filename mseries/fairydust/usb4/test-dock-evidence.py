#!/usr/bin/env python3
"""Offline regressions for route-aware diagnostics and frozen module evidence."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence = load('dock_evidence', HERE/'inspect-dock.py')
collect = load('dock_collect', HERE/'tools/collect-controlled-test.py')
repack = load('dock_repack', HERE/'tools/repack-dpin-initramfs.py')


class DockEvidence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.sys = self.root/'sys'
        self.proc = self.root/'proc'

    def route(self, address):
        controller = self.proc/'device-tree/soc'/('dcp@'+address)
        controller.mkdir(parents=True)
        (controller/'phandle').write_bytes(struct.pack('>I', 73))
        (controller/'apple,dp-tunnel').touch()
        nhi = self.proc/'device-tree/soc/cio@b01ac0000/nhi@f00000'
        nhi.mkdir(parents=True)
        (nhi/'apple,dp-source').write_bytes(struct.pack('>I', 73))
        (nhi/'apple,dp-in-port').write_bytes(struct.pack('>I', 5))

    def result(self, logs=None):
        return evidence.snapshot(self.sys, self.proc, logs, 'fixture')

    def test_absent_tree_and_logs_remain_unknown(self):
        result = self.result()
        self.assertFalse(result['link_configuration_observed'])
        self.assertIsNone(result['latest_mapped_source_result'])
        self.assertEqual(result['sources'], [])
        self.assertFalse(result['logs_available'])

    def test_e4_resolves_dcpext0_without_assuming_hdmi(self):
        self.route('289c00000')
        result = self.result('apple-dcp 289c00000.dcp: DPINDBG connect_source: waited=30 ret=0 powered=1 rate=30 lanes=4')
        self.assertEqual(result['sources'][0]['controller']['path'], '/soc/dcp@289c00000')
        self.assertTrue(result['link_configuration_observed'])
        self.assertFalse(result['picture_verified'])

    def test_builtin_hdmi_log_cannot_qualify_dcpext1_route(self):
        self.route('28cc00000')
        result = self.result('apple-dcp 289c00000.dcp: DPINDBG connect_source: waited=30 ret=0 powered=1 rate=30 lanes=4')
        self.assertFalse(result['link_configuration_observed'])

    def test_latest_failure_replaces_earlier_success(self):
        self.route('28cc00000')
        logs = ('apple-dcp 28cc00000.dcp: DPINDBG connect_source: waited=30 ret=0 powered=1 rate=30 lanes=4\n'
                'apple-dcp 28cc00000.dcp: DPINDBG connect_source: waited=20 ret=-67 powered=1 rate=0 lanes=4')
        self.assertFalse(self.result(logs)['link_configuration_observed'])

    def test_ret_zero_without_trained_rate_is_not_link_evidence(self):
        self.route('28cc00000')
        result = self.result('apple-dcp 28cc00000.dcp: DPINDBG connect_source: waited=30 ret=0 powered=1 rate=0 lanes=4')
        self.assertFalse(result['link_configuration_observed'])

    def test_flat_external_connectors_found_but_edp_excluded(self):
        for name in ('card2-eDP-1','card2-HDMI-A-1','card2-DP-1','card2-DP-1-1'):
            node = self.sys/'class/drm'/name
            node.mkdir(parents=True)
            (node/'status').write_text('connected')
            (node/'modes').write_text('1920x1080\n')
        connectors = self.result()['external_connectors']
        self.assertEqual(len(connectors), 3)
        self.assertTrue(all(not row['edid_valid'] for row in connectors))
        self.assertFalse(self.result()['picture_verified'])

    def test_edid_requires_declared_extension_blocks(self):
        node = self.sys/'class/drm/card2-DP-1'
        node.mkdir(parents=True)
        raw = bytearray(128)
        raw[:8] = bytes.fromhex('00ffffffffffff00')
        raw[126] = 1  # extension missing, despite a valid base checksum
        raw[127] = (-sum(raw)) % 256
        (node/'edid').write_bytes(raw)
        self.assertFalse(self.result()['external_connectors'][0]['edid_valid'])
        raw[126] = 0
        raw[127] = 0
        raw[127] = (-sum(raw)) % 256
        (node/'edid').write_bytes(raw)
        self.assertTrue(self.result()['external_connectors'][0]['edid_valid'])

    def test_malformed_phandle_does_not_crash(self):
        self.route('28cc00000')
        (self.proc/'device-tree/soc/dcp@28cc00000/phandle').write_bytes(b'bad')
        self.assertIsNone(self.result()['sources'][0]['controller'])


class FrozenIdentity(unittest.TestCase):
    def test_changed_input_cannot_be_reported_as_frozen_match(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'appledrm.ko'
            path.write_bytes(b'changed')
            manifest = {'inputs': {str(path): hashlib.sha256(b'original').hexdigest()}}
            result = collect.module_identity('appledrm.ko', manifest, Path(directory))
            self.assertFalse(result['matches_frozen_bundle'])
            self.assertIn('changed', result['error'])

    def test_note_validation_and_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root/'appledrm.ko'
            path.write_bytes(b'original')
            manifest = {'inputs': {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}}
            note = root/'module/appledrm/notes/.note.gnu.build-id'
            note.parent.mkdir(parents=True)
            raw = struct.pack('<III',4,2,3) + b'GNU\0' + b'\xab\xcd'
            with patch.object(collect, 'run', return_value={'returncode':0,'stdout':'Build ID: abcd'}):
                note.write_bytes(raw)
                self.assertTrue(collect.module_identity('appledrm.ko', manifest, root)['matches_frozen_bundle'])
                note.write_bytes(raw[:-1])
                self.assertFalse(collect.module_identity('appledrm.ko', manifest, root)['matches_frozen_bundle'])


class ArchivePaths(unittest.TestCase):
    def test_equivalent_names_have_one_canonical_path(self):
        self.assertEqual(repack.canonical('./usr//lib/./modules/'), 'usr/lib/modules')
        for path in ('../outside', '/boot/file', 'a\0b'):
            with self.assertRaises(ValueError):
                repack.canonical(path)

    def test_new_file_under_symlink_parent_is_rejected(self):
        import gzip
        import stat
        with tempfile.TemporaryDirectory() as directory:
            replacement = Path(directory)/'file'
            replacement.write_bytes(b'module')
            vals = [1,stat.S_IFLNK|0o777,0,0,1,0,0,0,0,0,0,0,0]
            trailer = [0]*13
            image = gzip.compress(repack.encode([('usr/lib',vals,b'/outside')],trailer))
            with self.assertRaisesRegex(ValueError,'not a directory'):
                repack.repack(image,{'usr/lib/new.ko':str(replacement)})


if __name__ == '__main__':
    unittest.main()
