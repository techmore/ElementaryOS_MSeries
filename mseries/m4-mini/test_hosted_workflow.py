#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check hosted Mesa prerequisites against the independent successful local capture."""
import json
from pathlib import Path
import shlex
import unittest
import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


class HostedDependencyTests(unittest.TestCase):
    def test_all_captured_local_dependencies_are_explicit(self):
        workflow = yaml.load((REPO / '.github/workflows/daily-9.0.yml').read_text(), Loader=yaml.BaseLoader)
        step = next(step for step in workflow['jobs']['build-m4-userspace']['steps']
                    if step.get('name') == 'Install Mesa build and software-test dependencies')
        packages = set(shlex.split(step['run'].replace('\\\n', ' ')))
        captured = json.loads((HERE / 'receipts/2026-10-21-mesa-configure.json').read_text())
        required = {item['file'].split('_')[0] for item in captured['work_local_dependencies']}
        self.assertFalse(required - packages, 'missing captured dependencies: ' + str(required - packages))


if __name__ == '__main__':
    unittest.main()
