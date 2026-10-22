#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prevent graph summaries from accepting packages outside their pinned profile."""
import copy
import importlib.util
from pathlib import Path
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('image_driver', HERE / 'build-research-image.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ProfileVersionTests(unittest.TestCase):
    def setUp(self):
        self.profile = (module.REPO / module.PROFILE).read_text()
        import re
        self.controls = {kind: {'Package': name, 'Architecture': 'arm64',
            'Version': re.search(r'^\s+' + re.escape(name) + r'=([^\s]+)',
                                 self.profile, re.MULTILINE)[1]}
            for kind, name in module.PACKAGE_NAMES.items()}

    def test_matching_profile_and_artifacts(self):
        self.assertEqual(module.profile_package_versions(self.profile, self.controls),
                         {k: v['Version'] for k, v in self.controls.items()})

    def test_new_mesa_artifact_requires_explicit_profile_selection(self):
        changed = copy.deepcopy(self.controls)
        changed['mesa']['Version'] += '.unselected'
        with self.assertRaisesRegex(ValueError, 'version differs'):
            module.profile_package_versions(self.profile, changed)
        selected = self.profile.replace(self.controls['mesa']['Version'], changed['mesa']['Version'])
        self.assertEqual(module.profile_package_versions(selected, changed)['mesa'],
                         changed['mesa']['Version'])

    def test_mismatched_identity_architecture_and_incomplete_inputs(self):
        for field, value in [('Package', 'unrelated-mesa'), ('Architecture', 'amd64')]:
            changed = copy.deepcopy(self.controls)
            changed['mesa'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                module.profile_package_versions(self.profile, changed)
        changed = copy.deepcopy(self.controls)
        del changed['policy']
        with self.assertRaises(ValueError):
            module.profile_package_versions(self.profile, changed)

    def test_missing_or_duplicate_version_pin_is_rejected(self):
        pin = '\n    ' + self.controls['mesa']['Package'] + '=' + self.controls['mesa']['Version']
        for profile in [self.profile.replace(pin, ''), self.profile + pin + '\n']:
            with self.assertRaises(ValueError):
                module.profile_package_versions(profile, self.controls)


if __name__ == '__main__':
    unittest.main()
