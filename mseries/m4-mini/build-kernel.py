#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the pinned Gravity mini research kernel in a new work directory."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

HERE = Path(__file__).resolve().parent
ARCHIVE_SHA256 = '045c64540fa4210394c899cad6320c5bf9090a66919938d986aeaad0033946e8'
COMMIT = '4fc326f6c25ccceb7515e2635c22e01fde5d3bac'
RELEASE = '7.1.13-elementary-m4-gravity1'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def packaging_patches():
    directory = HERE / 'gravity/patches'
    manifest = json.loads((directory / 'manifest.json').read_text())
    for name, expected in manifest.items():
        path = directory / name
        if Path(name).name != name or digest(path) != expected:
            raise ValueError('Gravity packaging patch checksum mismatch: ' + name)
    return directory, manifest



def compatibility_patches(version=None):
    directory = HERE / 'gravity/compatibility'
    manifest = (json.loads((directory / 'manifest.json').read_text()) if version is None else
                json.loads((directory / 'package-versions.json').read_text())[version])
    for name, expected in manifest.items():
        if Path(name).name != name or digest(directory / name) != expected:
            raise ValueError('elementary compatibility patch checksum mismatch')
    return directory, manifest


def source_patch_gate(source, compatibility_version=None):
    expected = json.loads((HERE / 'gravity/patches/resulting-files.json').read_text())
    directory = HERE / 'gravity/compatibility'
    if compatibility_version is None:
        compatibility = json.loads((directory / 'resulting-files.json').read_text())
        selected_patches = json.loads((directory / 'manifest.json').read_text())
    else:
        compatibility = json.loads((directory / 'resulting-files-by-version.json').read_text())[compatibility_version]
        selected_patches = json.loads((directory / 'package-versions.json').read_text())[compatibility_version]
    expected.update(compatibility)
    for name, value in expected.items():
        if digest(source / name) != value:
            raise ValueError('matched ARM64 packaging exports required: ' + name)

    contracts = {}
    if '0008-apple-m4-wfi-before-first-idle.patch' in selected_patches:
        idle = (source / 'arch/arm64/kernel/idle.c').read_text()
        smp = (source / 'arch/arm64/kernel/smp.c').read_text()
        boot = smp.split('void __init smp_prepare_boot_cpu(void)', 1)[1].split('\n}', 1)[0]
        if ('early_initcall(apple_wfi_quirk_init)' in idle
                or 'static bool apple_wfi_loses_regs __ro_after_init;' not in idle
                or 'return unlikely(READ_ONCE(apple_wfi_loses_regs));' not in idle
                or not all(token in boot for token in ['setup_boot_cpu_features();',
                                                       'apple_wfi_quirk_init();',
                                                       'kasan_init_hw_tags();'])
                or not (boot.index('setup_boot_cpu_features();')
                        < boot.index('apple_wfi_quirk_init();')
                        < boot.index('kasan_init_hw_tags();'))):
            raise ValueError('Apple M4 WFI selection must be initialized before boot CPU idle')
        contracts['boot_cpu_wfi_selection_before_first_idle'] = True

    if '0010-bcm4388-wait-for-wifi.patch' in selected_patches:
        bluetooth = (source / 'drivers/bluetooth/hci_bcm4377.c').read_text()
        probe = bluetooth.split('static int bcm4377_probe(struct pci_dev *pdev', 1)[1].split('\n}', 1)[0]
        if ('static int bcm4377_wait_for_wlan(' not in bluetooth
                or 'device_is_bound(&wlan->dev)' not in bluetooth
                or '-EPROBE_DEFER' not in bluetooth
                or 'bcm4377_wait_for_wlan(pdev, &bcm4377_hw_variants[id->driver_data])' not in probe
                or not (probe.index('bcm4377_wait_for_wlan(')
                        < probe.index('dma_set_mask_and_coherent('))):
            raise ValueError('BCM4388 Bluetooth must defer until its Wi-Fi function binds')
        contracts['bcm4388_waits_for_wifi_function'] = True
    return contracts


def config_gate(path):
    values = dict(line.split('=', 1) for line in path.read_text().splitlines()
                  if line.startswith('CONFIG_') and '=' in line)
    for key, value in {'CONFIG_ARCH_APPLE': 'y', 'CONFIG_ARM64_16K_PAGES': 'y',
                       'CONFIG_BLK_DEV_SR': 'y', 'CONFIG_ISO9660_FS': 'y',
                       'CONFIG_APPLE_WATCHDOG': 'y',
                       'CONFIG_DRM_ASAHI_M4': 'm',
                       'CONFIG_RUST': 'y', 'CONFIG_DRM_APPLE': 'm',
                       'CONFIG_AQTION': 'm', 'CONFIG_TIGON3': 'm',
                       'CONFIG_LOCALVERSION': '"-elementary-m4-gravity1"'}.items():
        if values.get(key) != value:
            raise ValueError(f'resolved configuration must have {key}={value}')


def check_apple_idle_image(build, output):
    vmlinux = build / 'vmlinux'
    if not vmlinux.is_file():
        raise ValueError('linked vmlinux required for Apple idle verification')
    nm = shutil.which('nm')
    objdump = shutil.which('llvm-objdump') or shutil.which('objdump')
    strings = shutil.which('strings')
    if not nm or not objdump or not strings:
        raise ValueError('nm, objdump and strings are required for Apple idle verification')
    symbols = subprocess.check_output([nm, str(vmlinux)], text=True)
    if not re.search(r'\bapple_cpu_wfi$', symbols, re.MULTILINE):
        raise ValueError('linked apple_cpu_wfi symbol is missing')
    if not re.search(r'\bapple_wfi_quirk_init$', symbols, re.MULTILINE):
        raise ValueError('linked early Apple WFI selector is missing')
    if Path(objdump).name.startswith('llvm-'):
        disassembly = subprocess.check_output([objdump, '--disassemble-symbols=apple_cpu_wfi', str(vmlinux)], text=True)
    else:
        disassembly = subprocess.check_output([objdump, '-d', '--disassemble=apple_cpu_wfi', str(vmlinux)], text=True)
    required = ['dsb', 'wfi', 'isb', 'stp', 'str', 'ldp', 'x18', 'x19', 'x28', 'x29', 'x30']
    missing = [token for token in required if not re.search(r'\b' + token + r'\b', disassembly.lower())]
    if missing:
        raise ValueError('apple_cpu_wfi disassembly lacks required instruction/registers: ' + ', '.join(missing))
    output.write_text(disassembly)
    literals = subprocess.check_output([strings, str(vmlinux)], text=True, errors='replace')
    if 'id_aa64isar2.wfxt=0' not in literals:
        raise ValueError('compiled Apple WFxT override literal is missing')
    return {'apple_cpu_wfi_linked': True, 'apple_wfi_quirk_init_linked': True,
            'state_save_restore_instructions_present': True,
            'm4_wfxt_override_literal_present': True, 'disassembly_sha256': digest(output)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--rust-library', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1 or args.output.exists():
        raise ValueError('positive jobs and a new output directory required')
    if digest(args.archive) != ARCHIVE_SHA256:
        raise ValueError('Gravity source archive checksum mismatch')
    if not (args.rust_library / 'core/src/lib.rs').is_file():
        raise ValueError('matching Rust library sources required')
    root = args.output.resolve()
    root.mkdir(parents=True)
    source, build = root / ('linux-' + COMMIT), root / 'build'
    with tarfile.open(args.archive) as archive:
        if any(Path(member.name).parts[0] != 'linux-' + COMMIT for member in archive):
            raise ValueError('unexpected archive root')
        archive.extractall(root, filter='data')
    patch_directory, patches = packaging_patches()
    for name in patches:
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source),
                        '-i', str(patch_directory / name)], check=True)
    compatibility_directory, compatibility = compatibility_patches()
    for name in compatibility:
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-d', str(source),
                        '-i', str(compatibility_directory / name)], check=True)
    source_contracts = source_patch_gate(source)
    build.mkdir()
    env = dict(os.environ, RUST_LIB_SRC=str(args.rust_library.resolve()))
    base = ['make', '-C', str(source), f'O={build}', 'ARCH=arm64',
            'CC=clang', 'LD=ld', 'HOSTCC=clang']
    def run(command):
        with (root / 'build.log').open('ab') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    run(base + ['defconfig', 'asahi.config'])
    run([str(source / 'scripts/kconfig/merge_config.sh'), '-m', '-O', str(build),
         str(build / '.config'), str(HERE / 'gravity/gravity.config'),
         str(HERE / 'gravity/gravity-aarch64.config'),
         str(HERE / 'gravity/elementary-target.config')])
    run([str(source / 'scripts/config'), '--file', str(build / '.config'),
         '--set-str', 'LOCALVERSION', '-elementary-m4-gravity1', '--disable', 'LOCALVERSION_AUTO'])
    run(base + ['olddefconfig'])
    config_gate(build / '.config')
    run(base + [f'-j{args.jobs}', 'Image', 'modules', 'dtbs'])
    idle_checks = check_apple_idle_image(build, root / 'apple-idle-disassembly.txt')
    artifacts = ['arch/arm64/boot/Image', 'drivers/gpu/drm/asahi/asahi_m4.ko',
                 'arch/arm64/boot/dts/apple/t8132-j773g.dtb',
                 'drivers/net/ethernet/aquantia/atlantic/atlantic.ko',
                 'drivers/net/ethernet/broadcom/tg3.ko']
    hashes = {path: digest(build / path) for path in artifacts}
    receipt = {'repository': 'GravityLinux/linux', 'commit': COMMIT,
               'source_archive_sha256': ARCHIVE_SHA256, 'kernel_release': RELEASE,
               'config_sha256': digest(build / '.config'), 'artifacts': hashes,
               'packaging_patches': patches, 'compatibility_patches': compatibility,
               'm4_idle_checks': idle_checks, 'source_contracts': source_contracts,
               'status': 'source build only; no installation or J773g hardware qualification'}
    (root / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
