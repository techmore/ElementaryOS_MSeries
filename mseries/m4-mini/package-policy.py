#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package the candidate M4 image's vendor sleep policy; never install it."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
NAME = 'elementary-m4-gravity-policy'
VERSION = '20261021-2'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new output directory required')
    args.output.mkdir(parents=True)
    source = HERE / 'gravity/policy'
    manifest = {}
    with tempfile.TemporaryDirectory(prefix='m4-policy-') as temp:
        payload = Path(temp)
        files = {
            'systemd/sleep.conf.d/90-gravity-no-sleep.conf': '90-gravity-no-sleep.conf',
            'systemd/logind.conf.d/90-gravity-no-sleep-logind.conf': '90-gravity-no-sleep-logind.conf',
        }
        for unit in ['suspend', 'hibernate', 'hybrid-sleep', 'suspend-then-hibernate']:
            files[f'systemd/system/systemd-{unit}.service.d/90-gravity-block-sleep.conf'] = '90-gravity-block-sleep-service.conf'
        for target, original in files.items():
            path = payload / 'usr/lib' / target
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / original, path)
            manifest['usr/lib/' + target] = hashlib.sha256(path.read_bytes()).hexdigest()
        early = payload / 'usr/share/initramfs-tools/modules.d/elementary-m4'
        early.parent.mkdir(parents=True, exist_ok=True)
        early.write_text('# M4 mini storage and early Apple input drivers.\nnvme_apple\npcie_apple\nhid_apple\nhid_magicmouse\n')
        manifest[str(early.relative_to(payload))] = hashlib.sha256(early.read_bytes()).hexdigest()
        docs = payload / 'usr/share/doc' / NAME
        shutil.copytree(source, docs)
        (docs / 'README').write_text('Candidate M4 mini image policy only. No local installation or hardware sleep qualification.\nRemoval via package upgrade is required when M4 sleep is supported.\nAdministrator configuration overrides vendor settings.\n')
        control = payload / 'DEBIAN'
        control.mkdir()
        (control / 'control').write_text(f'Package: {NAME}\nVersion: {VERSION}\nArchitecture: arm64\nMaintainer: ElementaryOS MSeries contributors <builder@localhost>\nDepends: systemd, initramfs-tools, linux-image-elementary-m4-gravity1\nSection: admin\nPriority: optional\nDescription: Temporary power and early-driver policy for M4 mini images\n Disables unsupported system sleep through vendor configuration.\n')
        package = args.output / f'{NAME}_{VERSION}_arm64.deb'
        subprocess.run(['dpkg-deb', '--root-owner-group', '--build', str(payload), str(package)], check=True)
    (args.output / 'receipt.json').write_text(json.dumps({
        'package': package.name, 'package_sha256': hashlib.sha256(package.read_bytes()).hexdigest(),
        'upstream_commit': '711c2a110416d28010ccdd118b83111776bff207',
        'vendor_files': manifest, 'maintainer_scripts': False,
        'status': 'candidate image policy packaged; no installation or hardware qualification',
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
