#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble verified M4 package payloads in a new root; never install or boot."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
RECEIPTS = {
    'kernel': '2026-10-21-gravity-kernel-package.json',
    'mesa': '2026-10-21-gravity-mesa-package-r3.json',
    'policy': '2026-10-21-m4-sleep-policy.json',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in RECEIPTS:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new output directory required')
    packages = {}
    for name, filename in RECEIPTS.items():
        receipt = json.loads((HERE / 'receipts' / filename).read_text())
        package = getattr(args, name)
        with package.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != receipt['package_sha256']:
            raise ValueError('verified package required: ' + name)
        packages[name] = {'package': receipt['package'], 'sha256': actual}
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    root = args.output / 'root'
    root.mkdir()
    for name in packages:
        subprocess.run(['dpkg-deb', '--extract', str(getattr(args, name)), str(root)], check=True)
    modules = root / 'usr/lib/modules/7.1.13-elementary-m4-gravity1'
    if len(list(modules.rglob('*.ko'))) != 1598:
        raise ValueError('combined module inventory mismatch')
    for module in ['asahi_m4', 'appledrm', 'atlantic', 'tg3']:
        result = subprocess.run(['modprobe', '-d', str(root / 'usr'), '-S', modules.name,
                                 '--show-depends', module], capture_output=True, text=True, check=True)
        if 'insmod ' not in result.stdout:
            raise ValueError('module resolution failed: ' + module)
    result = {'packages': packages, 'module_count': 1598,
              'module_dependency_dry_run': 'passed for asahi_m4, appledrm, atlantic, tg3',
              'status': 'payload overlay assembled only; no base OS, initramfs, EFI or firmware',
              'base_os_dependencies_resolved': False, 'installer_admission': False,
              'hardware_validated': False}
    (args.output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    marker.unlink()


if __name__ == '__main__':
    main()
