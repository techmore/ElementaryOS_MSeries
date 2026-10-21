#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Assemble a research ARM64 UKI from verified M4 inputs; never install it."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess

HERE = Path(__file__).resolve().parent
RELEASE = '7.1.13-elementary-m4-gravity1'
spec = importlib.util.spec_from_file_location('uki_input', HERE.parent / 'boot/prepare-uki-kernels.py')
pe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pe)
OS_RELEASE = ('NAME="elementary OS M4 research candidate"\nID=elementary-m4-research\n'
              'VERSION_ID=20261021\nPRETTY_NAME="elementary OS M4 research candidate"\n')


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['tools', 'kernel', 'initramfs', 'cmdline', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new output required')
    tool_receipt = json.loads((HERE / 'receipts/2026-10-21-efi-tools.json').read_text())
    for name, expected in tool_receipt['files'].items():
        if digest(args.tools / name) != expected:
            raise ValueError('EFI tool checksum mismatch: ' + name)
    kernel_receipt = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
    if digest(args.kernel) != kernel_receipt['artifacts']['arch/arm64/boot/Image']:
        raise ValueError('verified M4 kernel required')
    if (args.initramfs / 'INCOMPLETE').exists():
        raise ValueError('completed initramfs output required')
    initrd_receipt = json.loads((args.initramfs / 'receipt.json').read_text())
    initrd = args.initramfs / ('initrd-' + RELEASE + '.img')
    if initrd_receipt['kernel_release'] != RELEASE or digest(initrd) != initrd_receipt['initramfs_sha256']:
        raise ValueError('matching validated initramfs required')
    cmdline = args.cmdline.read_text().strip()
    roots = [value for value in shlex.split(cmdline) if value.startswith('root=')]
    if '\n' in cmdline or '\0' in cmdline or len(roots) != 1 or not roots[0][5:]:
        raise ValueError('one explicit root= target required on a single command line')
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    osrel = args.output / 'os-release'
    osrel.write_text(OS_RELEASE)
    (args.output / 'cmdline').write_text(cmdline + '\n')
    extracted = args.tools.resolve() / 'extracted'
    ukify = extracted / 'usr/lib/systemd/ukify'
    stub = extracted / 'usr/lib/systemd/boot/efi/linuxaa64.efi.stub'
    output = args.output / 'elementary-m4-research.efi'
    env = dict(os.environ, PYTHONPATH=str(extracted / 'usr/lib/python3/dist-packages'))
    command = ['python3', str(ukify), 'build', '--config=/dev/null', '--efi-arch=aa64',
               '--stub=' + str(stub), '--linux=' + str(args.kernel.resolve()),
               '--initrd=' + str(initrd.resolve()), '--uname=' + RELEASE,
               '--cmdline=@' + str((args.output / 'cmdline').resolve()),
               '--os-release=@' + str(osrel.resolve()), '--output=' + str(output.resolve())]
    with (args.output / 'build.log').open('wb') as stream:
        subprocess.run(command, env=env, stdout=stream, stderr=subprocess.STDOUT, check=True)
    sections, relocations = pe.pe_sections(output.read_bytes())
    for name, expected in [('.linux', args.kernel.read_bytes()), ('.initrd', initrd.read_bytes())]:
        if sections.get(name) != expected:
            raise ValueError('embedded payload mismatch: ' + name)
    for name, expected in [('.cmdline', cmdline), ('.uname', RELEASE), ('.osrel', OS_RELEASE.strip())]:
        if sections[name].rstrip(b'\0\n').decode() != expected:
            raise ValueError('embedded metadata mismatch: ' + name)
    if {'.dtb', '.dtbauto'} & sections.keys():
        raise ValueError('static DTB must not override matched bootloader fixups')
    (args.output / 'receipt.json').write_text(json.dumps({
        'kernel_release': RELEASE, 'uki_sha256': digest(output), 'kernel_sha256': digest(args.kernel),
        'initramfs_sha256': digest(initrd), 'sections': list(sections), 'cmdline': cmdline,
        'stub_sha256': digest(stub), 'relocation_directory_size': relocations,
        'embedded_payloads': 'exact kernel/initramfs bytes and metadata verified',
        'status': 'unsigned research EFI assembled only; no boot entries, partition writes or hardware qualification',
        'hardware_validated': False,
    }, indent=2) + '\n')
    marker.unlink()


if __name__ == '__main__':
    main()
