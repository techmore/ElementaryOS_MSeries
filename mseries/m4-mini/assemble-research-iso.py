#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble and read back an unpromoted M4 live ISO on an ephemeral ARM64 runner.

Consumes the complete build-research-image.py workspace. Never writes devices,
installs boot software on the host, or admits the Apple installer.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import struct
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hosted-root', action='store_true')
    args = parser.parse_args()
    if not (args.hosted_root and os.geteuid() == 0 and
            os.environ.get('GITHUB_ACTIONS') == 'true' and platform.machine() == 'aarch64'):
        raise ValueError('assembly requires explicit ephemeral ARM64 GitHub hosted root')
    workspace = args.workspace.resolve()
    record = json.loads((workspace / 'receipt.json').read_text())
    if ((workspace / 'INCOMPLETE').exists() or not record['mkosi_build_passed'] or
            record['summary_only'] or record['hardware_validated'] or record['installer_admission']):
        raise ValueError('complete unpromoted research image build required')
    version = record['image_version']
    if not re.fullmatch(r'[0-9]{14}', version):
        raise ValueError('invalid image version')
    images = workspace / 'images'
    live = images / ('liveiso_' + version)
    raw = images / ('elementary_' + version + '.raw')
    build = json.loads((workspace / 'input-records/kernel-build.json').read_text())
    release = build['kernel_release']
    if not re.fullmatch(r'[A-Za-z0-9.+_-]+', release):
        raise ValueError('invalid kernel release')
    modules = live / 'usr/lib/modules'
    if sorted(p.name for p in modules.iterdir() if p.is_dir()) != [release]:
        raise ValueError('exactly one matched research kernel required')
    kernel = live / ('boot/vmlinuz-' + release)
    initrd = live / ('boot/initrd.img-' + release)
    expected_kernel = build['artifacts']['arch/arm64/boot/Image']
    if digest(kernel) != expected_kernel or digest(modules / release / 'vmlinuz') != expected_kernel:
        raise ValueError('live kernel differs from reviewed component')
    if not initrd.is_file() or initrd.stat().st_size == 0 or not raw.is_file():
        raise ValueError('complete initramfs and raw system image required')
    installer = live / 'usr/sbin/elementary-install'
    guard = workspace / 'source/mkosi.images/liveiso/mkosi.profiles/m4-mini/mkosi.extra/usr/sbin/elementary-install'
    if digest(installer) != digest(guard):
        raise ValueError('research installer admission guard required')
    output = args.output.resolve()
    if output.exists() or output == workspace or output.is_relative_to(live):
        raise ValueError('new output directory outside live root required')
    for tool in ['mksquashfs', 'grub-mkrescue', 'xorriso', 'unsquashfs', 'lsinitramfs',
                 'mformat', 'mcopy']:
        if not shutil.which(tool):
            raise ValueError('missing assembly tool: ' + tool)
    if not Path('/usr/lib/grub/arm64-efi/modinfo.sh').is_file():
        raise ValueError('ARM64 EFI GRUB modules required')
    output.mkdir(parents=True)
    marker = output / 'INCOMPLETE'
    marker.touch()
    commands = []

    def run(command, name):
        commands.append(command)
        with (output / (name + '.log')).open('wb') as log:
            subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, check=True)

    # The build hook generated the initramfs already. Do not mutate the checked root.
    run(['lsinitramfs', str(initrd)], 'initramfs')
    initramfs = (output / 'initramfs.log').read_text()
    for name in ['nvme-apple', 'pcie-apple']:
        if name not in initramfs.replace('_', '-'):
            raise ValueError('missing early boot module: ' + name)
    root = output / 'iso_root'
    shutil.copytree(live / 'iso_root', root, symlinks=True)
    os_release = {}
    for line in (images / ('base_' + version) / 'usr/lib/os-release').read_text().splitlines():
        if '=' in line and not line.startswith('#'):
            key, value = line.split('=', 1)
            parsed = shlex.split(value)
            if len(parsed) == 1:
                os_release[key] = parsed[0]
    title = os_release['PRETTY_NAME']
    # Titles are interpolated into a double-quoted GRUB menu entry.
    if any(c in title for c in ['"', '\\', '$', '\n', '\r']):
        raise ValueError('unsupported GRUB title characters')
    for relative in ['boot/grub/grub.cfg', '.disk/info']:
        p = root / relative
        value = p.read_text().replace('%PLACEHOLDER_VERSION%', title).replace('%PLACEHOLDER_ARCH%', 'arm64')
        if '%PLACEHOLDER_' in value:
            raise ValueError('unresolved live ISO placeholder')
        p.write_text(value)
    (root / 'casper').mkdir(exist_ok=True)
    (root / 'extra').mkdir(exist_ok=True)
    shutil.copy2(kernel, root / 'casper/vmlinuz')
    shutil.copy2(initrd, root / 'casper/initrd')
    package_index = root / 'dists/stable/main/binary-arm64/Packages'
    package_index.parent.mkdir(parents=True, exist_ok=True)
    package_index.touch()
    (root / 'pool').mkdir(exist_ok=True)
    run(['mksquashfs', str(live), str(root / 'casper/filesystem.squashfs'),
         '-noappend', '-comp', 'zstd', '-Xcompression-level', '3', '-processors', '2',
         '-e', 'iso_root'], 'live-squashfs')
    embedded = root / 'extra' / (raw.name + '.squashfs')
    run(['mksquashfs', str(raw), str(embedded), '-noappend', '-comp', 'zstd',
         '-Xcompression-level', '3', '-processors', '2'], 'raw-squashfs')
    iso = output / ('elementaryos-9.0-m4-mini-research-arm64.' + version + '.iso')
    run(['grub-mkrescue', '--directory=/usr/lib/grub/arm64-efi', '-o', str(iso),
         '-iso-level', '3', '-volid', 'ELEMENTARY_M4_MINI_ARM64', str(root)], 'iso-assembly')
    run(['xorriso', '-indev', str(iso), '-report_el_torito', 'plain'], 'iso-boot-catalog')
    catalog = (output / 'iso-boot-catalog.log').read_text()
    if 'UEFI' not in catalog:
        raise ValueError('ISO lacks a reported UEFI boot image')
    readback = output / 'readback'
    run(['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', '/', str(readback)], 'iso-readback')
    efi = output / 'bootaa64.efi'
    run(['mcopy', '-i', str(readback / 'efi.img'), '::EFI/BOOT/BOOTAA64.EFI', str(efi)], 'efi-readback')
    efi_bytes = efi.read_bytes()
    pe = struct.unpack_from('<I', efi_bytes, 0x3c)[0]
    if (efi_bytes[:2] != b'MZ' or efi_bytes[pe:pe + 4] != b'PE\0\0' or
            struct.unpack_from('<H', efi_bytes, pe + 4)[0] != 0xaa64):
        raise ValueError('ISO EFI fallback executable is not AArch64 PE')
    payloads = ['casper/vmlinuz', 'casper/initrd', 'casper/filesystem.squashfs',
                'extra/' + embedded.name, 'boot/grub/grub.cfg']
    hashes = {name: digest(root / name) for name in payloads}
    if any(digest(readback / name) != value for name, value in hashes.items()):
        raise ValueError('ISO readback payload mismatch')
    command = ['unsquashfs', '-cat', str(readback / ('extra/' + embedded.name)), raw.name]
    commands.append(command)
    raw_digest = hashlib.sha256()
    with (output / 'raw-readback.log').open('wb') as log:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log) as process:
            while chunk := process.stdout.read(1024 * 1024):
                raw_digest.update(chunk)
            if process.wait() != 0:
                raise ValueError('embedded raw system image extraction failed')
    if raw_digest.hexdigest() != digest(raw):
        raise ValueError('embedded raw system image differs')
    shutil.rmtree(readback)
    (output / 'receipt.json').write_text(json.dumps({
        'scope': 'assembled ARM64 UEFI research ISO and independent filesystem payload readback; no boot',
        'source_commit': record['source_commit'], 'image_version': version,
        'assembler_sha256': digest(Path(__file__)), 'kernel_release': release,
        'iso_file': iso.name, 'iso_sha256': digest(iso), 'payload_sha256': hashes,
        'efi_boot_path': 'EFI/BOOT/BOOTAA64.EFI', 'efi_pe_machine': '0xaa64 AArch64',
        'efi_sha256': digest(efi),
        'raw_image_sha256': digest(raw), 'commands': commands,
        'iso_assembled': True, 'iso_boot_tested': False, 'factory_promotion': False,
        'installer_admission': False, 'hardware_validated': False}, indent=2) + '\n')
    marker.unlink()
    print('Research ISO assembled and read back; no boot or installer qualification')


if __name__ == '__main__':
    main()
