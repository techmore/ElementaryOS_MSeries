#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Resolve real mkosi configs for default/M4/conflicting profiles; builds no image."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--mkosi-source', type=Path, required=True)
args = parser.parse_args()
repo = Path(__file__).resolve().parents[2]
env = dict(os.environ, PYTHONPATH=str(args.mkosi_source.resolve()))


def resolve(*options):
    return subprocess.run([sys.executable, '-m', 'mkosi', '--image-version=20261021',
                           '--json', *options, 'summary'], cwd=repo, env=env,
                          capture_output=True, text=True)


def images(result):
    if result.returncode:
        raise RuntimeError(result.stderr)
    return {image['Image']: image for image in json.loads(result.stdout)['Images']}


default = images(resolve('--architecture=arm64'))
m4 = images(resolve('--architecture=arm64', '--profile=m4-mini'))
expected = {'linux-image-elementary-m4-gravity1=7.1.13+elementary.m4.gravity1-2',
            'elementary-m4-gravity-mesa1=26.3.0~devel+gravity.87ac51d-3',
            'elementary-m4-gravity-policy=20261021-2'}
assert 'linux-image-generic' in default['base']['Packages']
assert not any('gravity' in item for item in default['base']['Packages'])
assert set(m4['base']['Packages']) == (set(default['base']['Packages']) - {'linux-image-generic'}) | expected
for name in default:
    if name != 'base':
        assert set(default[name]['Packages']) == set(m4[name]['Packages']), name
assert set(m4['liveiso']['KernelInitrdModules']) == set(default['liveiso']['KernelInitrdModules']) | {
    'nvme_apple', 'pcie_apple', 'hid_apple', 'hid_magicmouse'}
wrong = resolve('--architecture=x86-64', '--profile=m4-mini')
assert wrong.returncode != 0 and 'Architecture=arm64 in [Assert]' in wrong.stderr
conflict = resolve('--architecture=arm64', '--profile=m4-mini', '--profile=fairydust')
assert conflict.returncode != 0 and 'Profiles=!fairydust in [Assert]' in conflict.stderr
fairydust = images(resolve('--architecture=arm64', '--profile=fairydust'))
assert 'linux-image-generic' in fairydust['base']['Packages']
assert not any('gravity' in item for item in fairydust['base']['Packages'])
print('Default, M4, Fairydust, wrong-architecture and conflicting-profile configuration checks passed')
