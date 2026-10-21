#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Replay the M4 live-kernel hook in an isolated root with casper configured."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
RELEASE = '7.1.13-elementary-m4-gravity1'
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--receipt', type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
if root == Path('/') or not (root / 'usr/share/initramfs-tools/scripts/casper').is_file():
    raise ValueError('isolated configured candidate root with casper required')
if args.receipt.exists():
    raise ValueError('new receipt required')
hook = HERE.parents[1] / 'mkosi.images/liveiso/mkosi.profiles/m4-mini/prepare-live-kernel.chroot'
with tempfile.TemporaryDirectory(prefix='m4-live-hook-', dir=root / 'tmp') as temp:
    staged = Path(temp) / 'hook'
    shutil.copy2(hook, staged)
    inside = '/' + str(staged.relative_to(root))
    script = r"""set -eu
mount --bind /dev/null "$1/dev/null"
mount -t proc -o ro,nosuid,nodev,noexec proc "$1/proc"
exec chroot "$1" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C "$2"
"""
    result = subprocess.run(['unshare', '--user', '--map-auto', '--map-root-user', '--mount', '--pid', '--fork',
                             '/bin/sh', '-c', script, 'm4-live-hook', str(root), inside],
                            check=True, capture_output=True, text=True)
image = root / 'boot' / ('vmlinuz-' + RELEASE)
initrd = root / 'boot' / ('initrd.img-' + RELEASE)
expected = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
digest = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
assert digest(image) == expected['artifacts']['arch/arm64/boot/Image']
inventory = set(subprocess.check_output(['lsinitramfs', str(initrd)], text=True).splitlines())
required = {'scripts/casper', 'scripts/casper-premount/20iso_scan', 'conf/modules'}
required |= {'usr/lib/modules/' + RELEASE + '/kernel/' + p for p in [
    'drivers/nvme/host/nvme-apple.ko', 'drivers/pci/controller/pcie-apple.ko',
    'drivers/hid/hid-apple.ko', 'drivers/hid/hid-magicmouse.ko', 'fs/overlayfs/overlay.ko']}
assert required <= inventory, required - inventory
with tempfile.TemporaryDirectory(prefix='m4-live-inspect-') as temp:
    subprocess.run(['unmkinitramfs', str(initrd), temp], check=True)
    configs = list(Path(temp).rglob('conf/modules'))
    assert len(configs) == 1
    early = {line.strip() for line in configs[0].read_text().splitlines()}
    assert {'nvme_apple', 'pcie_apple', 'hid_apple', 'hid_magicmouse'} <= early
warnings = [line for line in (result.stdout + result.stderr).splitlines() if line.startswith('W:')]
args.receipt.write_text(json.dumps({'kernel_sha256': digest(image), 'initramfs_sha256': digest(initrd),
    'hook_sha256': digest(hook), 'required_contents': sorted(required), 'warnings': warnings,
    'scope': 'real live hook replay and casper initramfs inspection in isolated configured ARM64 root',
    'full_factory_iso_built': False, 'hardware_validated': False}, indent=2) + '\n')
print('Live hook, pinned Image, casper scripts, overlay and early Apple driver checks passed')
