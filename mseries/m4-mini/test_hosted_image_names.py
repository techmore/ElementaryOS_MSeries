#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Receipt-name intake boundaries across independently packaged revisions."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('hosted_names', HERE / 'prepare-hosted-image-inputs.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class HostedImageNames(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='m4-hosted-names-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for kind in module.PREFIXES:
            (self.root / kind).mkdir()
            name = module.PREFIXES[kind] + 'fixture-2_arm64.deb'
            path = self.root / kind / name
            path.write_bytes(b'fixture package bytes, never installed')
            (self.root / kind / 'receipt.json').write_text(json.dumps({
                'package': name, 'package_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}))

    def test_new_revision_uses_receipt_not_previous_filename(self):
        directory = self.root / 'kernel'
        receipt = json.loads((directory / 'receipt.json').read_text())
        old = directory / receipt['package']
        receipt['package'] = receipt['package'].replace('fixture-2', 'fixture-5')
        old.rename(directory / receipt['package'])
        (directory / 'receipt.json').write_text(json.dumps(receipt))
        command = module.command(self.root, self.root / 'output')
        self.assertEqual(command[command.index('--kernel') + 1], str(directory / receipt['package']))
        self.assertEqual(command[1], str(HERE / 'prepare-image-inputs.py'))
        self.assertIn('--kernel-build-receipt', command)
        self.assertIn('--mesa-build-receipt', command)

    def test_unsafe_names_and_wrong_component_rejected(self):
        directory = self.root / 'kernel'
        receipt = json.loads((directory / 'receipt.json').read_text())
        for name in ['../outside_arm64.deb', '/absolute_arm64.deb', 'bad\\name_arm64.deb',
                     module.PREFIXES['mesa'] + 'fixture_arm64.deb', None]:
            with self.subTest(name=name):
                receipt['package'] = name
                (directory / 'receipt.json').write_text(json.dumps(receipt))
                with self.assertRaises(ValueError):
                    module.command(self.root, self.root / 'output')

    def test_changed_and_ambiguous_packages_rejected(self):
        directory = self.root / 'kernel'
        path = next(directory.glob('*.deb'))
        path.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            module.command(self.root, self.root / 'output')
        (directory / 'extra.deb').write_bytes(b'extra')
        with self.assertRaises(ValueError):
            module.command(self.root, self.root / 'output')

    def test_symlink_package_rejected(self):
        directory = self.root / 'kernel'
        path = next(directory.glob('*.deb'))
        outside = self.root / 'outside'
        path.rename(outside)
        path.symlink_to(outside)
        with self.assertRaises(ValueError):
            module.command(self.root, self.root / 'output')


if __name__ == '__main__':
    unittest.main()
