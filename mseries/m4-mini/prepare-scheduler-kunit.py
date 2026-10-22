#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepare a separate ARM64 QEMU KUnit source tree; never deploy a kernel."""
import argparse
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('kernel_build', HERE / 'build-kernel.py')
kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel)

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--experimental-owner', action='store_true', help='unpromoted allocation-owner candidate and seven-case test recipe')
args = parser.parse_args()
if args.output.exists() or kernel.digest(args.archive) != kernel.ARCHIVE_SHA256:
    raise ValueError('new output and pinned kernel archive required')
args.output.mkdir(parents=True)
marker = args.output / 'INCOMPLETE'
marker.touch()
with tarfile.open(args.archive) as archive:
    if any(Path(item.name).parts[0] != 'linux-' + kernel.COMMIT for item in archive):
        raise ValueError('unexpected kernel source root')
    archive.extractall(args.output, filter='data')
source = (args.output / ('linux-' + kernel.COMMIT)).resolve()
for directory, manifest in [kernel.packaging_patches(), kernel.compatibility_patches()]:
    for name in manifest:
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source), '-i', str(directory / name)], check=True)
kernel.source_patch_gate(source)
directory = HERE / 'gravity/testing'
manifest_name = 'manifest.json'
experimental = {}
if args.experimental_owner:
    directory = HERE / 'gravity/experimental/owner'
    experimental = json.loads((directory / 'manifest.json').read_text())
    for name, expected in experimental.items():
        if Path(name).name != name or kernel.digest(directory / name) != expected:
            raise ValueError('experimental owner patch mismatch')
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source), '-i', str(directory / name)], check=True)
    for name, expected in json.loads((directory / 'resulting-files.json').read_text()).items():
        if kernel.digest(source / name) != expected:
            raise ValueError('experimental owner source mismatch')
    manifest_name = 'test-manifest.json'
manifest = json.loads((directory / manifest_name).read_text())
for name, expected in manifest.items():
    if Path(name).name != name or kernel.digest(directory / name) != expected:
        raise ValueError('test patch mismatch')
    subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source), '-i', str(directory / name)], check=True)
shutil.copy2(HERE / 'gravity/testing/kunit.config', args.output / 'kunit.config')
(args.output / 'receipt.json').write_text(json.dumps({
    'scope': 'KUnit test-source preparation only; no compile/run/hardware result',
    'commit': kernel.COMMIT, 'source_archive_sha256': kernel.ARCHIVE_SHA256,
    'experimental_owner_patches': experimental,
    'test_patches': manifest, 'kunit_config_sha256': kernel.digest(args.output / 'kunit.config'), 'compatibility_patches': kernel.compatibility_patches()[1],
    'scheduler_test_source_sha256': kernel.digest(source / 'rust/kernel/drm/sched.rs'),
    'normal_kernel_package_modified': False, 'hardware_validated': False,
}, indent=2) + '\n')
marker.unlink()
print('Separate scheduler KUnit sources prepared; build/run results still required')
