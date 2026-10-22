#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Boot a hash-bound packaged 16KiB Image via GRUB EFI to a minimal QEMU PID1.

Requires previously inspected trusted package/build receipts. This fixture is
not the desktop ISO, Apple firmware, native M4 drivers or installer acceptance.
Only new workspace files and a networkless TCG guest are created.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import tarfile
import time

MARKER = 'ELEMENTARY_RESEARCH_KERNEL_QEMU_INIT_OK'
REJECTION = 'This 16 KB granular kernel is not supported by your CPU'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def cpio_entry(name, body, mode, inode, major=0, minor=0):
    name = name.encode() + b'\0'
    fields = [inode, mode, 0, 0, 1, 0, len(body), 0, 0, major, minor, len(name), 0]
    header = b'070701' + b''.join(f'{value:08x}'.encode() for value in fields) + name
    return header + b'\0' * (-len(header) % 4) + body + b'\0' * (-len(body) % 4)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package', type=Path, required=True)
    parser.add_argument('--package-receipt', type=Path, required=True)
    parser.add_argument('--build-receipt', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--firmware', type=Path, default=Path('/usr/share/qemu-efi-aarch64/QEMU_EFI.fd'))
    parser.add_argument('--grub-directory', type=Path, default=Path('/usr/lib/grub/arm64-efi'))
    parser.add_argument('--cpu', choices=['neoverse-n1', 'cortex-a72'], default='neoverse-n1')
    parser.add_argument('--expect-incompatible-pages', action='store_true')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if args.output.exists() or args.timeout < 1 or args.timeout > 300:
        raise ValueError('new output directory and bounded timeout required')
    if args.expect_incompatible_pages and args.cpu != 'cortex-a72':
        raise ValueError('negative page-size control requires cortex-a72')
    package = args.package.resolve()
    receipt = json.loads(args.package_receipt.read_text())
    build = json.loads(args.build_receipt.read_text())
    release = build['kernel_release']
    if (not package.is_file() or receipt['package'] != package.name or
            digest(package) != receipt['package_sha256'] or receipt['source_sha256'] != build['source_archive_sha256'] or
            receipt['kernel_release'] != release or
            not re.fullmatch(r'[A-Za-z0-9.+_-]+', release)):
        raise ValueError('matched regular package and trusted receipts required')
    expected = build['artifacts']['arch/arm64/boot/Image']
    if not re.fullmatch(r'[0-9a-f]{64}', expected) or not args.firmware.is_file():
        raise ValueError('expected Image hash and regular UEFI firmware required')
    for tool in ['cc', 'dpkg-deb', 'grub-mkrescue', 'xorriso', 'mformat', 'qemu-system-aarch64']:
        if not shutil.which(tool):
            raise ValueError('missing fixture tool: ' + tool)
    if not (args.grub_directory / 'modinfo.sh').is_file():
        raise ValueError('ARM64 GRUB modules required')
    output = args.output.resolve()
    output.mkdir(parents=True)
    marker = output / 'INCOMPLETE'
    marker.touch()
    root = output / 'iso_root'
    (root / 'boot/grub').mkdir(parents=True)
    (root / 'casper').mkdir()
    kernel = root / 'casper/vmlinuz'
    found = False
    with subprocess.Popen(['dpkg-deb', '--fsys-tarfile', str(package)], stdout=subprocess.PIPE) as process:
        with tarfile.open(fileobj=process.stdout, mode='r|') as archive:
            for member in archive:
                if member.name.lstrip('./') == 'usr/lib/modules/' + release + '/vmlinuz':
                    if found or not member.isfile() or member.size > 512 * 1024**2:
                        raise ValueError('invalid packaged Image member')
                    found = True
                    with kernel.open('wb') as target:
                        shutil.copyfileobj(archive.extractfile(member), target)
        if process.wait() != 0:
            raise ValueError('package stream failed')
    if not found or digest(kernel) != expected:
        raise ValueError('packaged Image differs from build receipt')
    with kernel.open('rb') as stream:
        header = stream.read(64)
    if header[56:60] != b'ARM\x64' or ((struct.unpack_from('<Q', header, 24)[0] >> 1) & 3) != 2:
        raise ValueError('16KiB ARM64 Image required')
    source = output / 'init.c'
    source.write_text('#include <stdio.h>\n#include <unistd.h>\n#include <sys/utsname.h>\n'
        '#include <sys/reboot.h>\n#include <string.h>\n'
        'int main(void) { struct utsname u; if (uname(&u) || strcmp(u.release,"' + release + '")) '
        '{ puts("WRONG_KERNEL"); fflush(stdout); for (;;) pause(); } '
        'printf("' + MARKER + ' release=%s\\n",u.release); fflush(stdout); '
        'sync(); reboot(RB_POWER_OFF); for (;;) pause(); }\n')
    commands = [['cc', '-static', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(output / 'init')]]
    subprocess.run(commands[-1], check=True)
    initrd = root / 'casper/initrd'
    initrd.write_bytes(cpio_entry('dev', b'', stat.S_IFDIR | 0o755, 1) +
        cpio_entry('dev/console', b'', stat.S_IFCHR | 0o600, 2, 5, 1) +
        cpio_entry('init', (output / 'init').read_bytes(), stat.S_IFREG | 0o755, 3) +
        cpio_entry('TRAILER!!!', b'', 0, 4))
    config = root / 'boot/grub/grub.cfg'
    config.write_text('set timeout=0\nset default=0\nmenuentry "Research kernel EFI fixture" {\n'
        ' echo ELEMENTARY_RESEARCH_ISO_GRUB_HANDOFF\n'
        ' linux /casper/vmlinuz console=ttyAMA0 earlycon=pl011,0x9000000 rdinit=/init panic=-1 loglevel=6\n'
        ' initrd /casper/initrd\n}\n')
    iso = output / 'fixture.iso'
    commands.append(['grub-mkrescue', '--directory=' + str(args.grub_directory.resolve()), '-o', str(iso),
                     '-iso-level', '3', '-volid', 'ELEMENTARY_M4_MINI_ARM64', str(root)])
    with (output / 'assemble.log').open('wb') as log:
        subprocess.run(commands[-1], stdout=log, stderr=subprocess.STDOUT, check=True)
    commands.append(['qemu-system-aarch64', '-machine', 'virt,accel=tcg', '-cpu', args.cpu,
        '-m', '1024', '-bios', str(args.firmware.resolve()), '-nographic', '-monitor', 'none',
        '-nic', 'none', '-no-reboot', '-device', 'virtio-scsi-pci,id=scsi',
        '-drive', 'file=' + str(iso) + ',if=none,id=cd,format=raw,media=cdrom,readonly=on',
        '-device', 'scsi-cd,drive=cd'])
    timed_out = False
    stopped_after_rejection = False
    log_path = output / 'qemu.log'
    with log_path.open('wb') as log:
        with subprocess.Popen(commands[-1], stdout=log, stderr=subprocess.STDOUT) as process:
            deadline = time.monotonic() + args.timeout
            while process.poll() is None:
                if args.expect_incompatible_pages and REJECTION in log_path.read_text(errors='replace'):
                    stopped_after_rejection = True
                    process.terminate()
                    break
                if time.monotonic() >= deadline:
                    timed_out = True
                    process.kill()
                    break
                time.sleep(0.1)
            try:
                code = process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait()
    text = log_path.read_text(errors='replace')
    seen = MARKER + ' release=' + release in text
    passed = (REJECTION in text and not seen and stopped_after_rejection and not timed_out
              if args.expect_incompatible_pages else seen and code == 0 and not timed_out)
    record = {'scope': 'packaged 16KiB kernel EFI/GRUB/minimal PID1 fixture on QEMU virt; no desktop or native M4',
        'commands': commands, 'kernel_package_sha256': digest(package), 'kernel_image_sha256': digest(kernel),
        'kernel_release': release, 'init_source_sha256': digest(source),
        'init_binary_sha256': digest(output / 'init'), 'initramfs_sha256': digest(initrd),
        'grub_config_sha256': digest(config), 'iso_sha256': digest(iso),
        'firmware_sha256': digest(args.firmware), 'runner_sha256': digest(Path(__file__)),
        'qemu_version': subprocess.check_output(['qemu-system-aarch64', '--version'], text=True).splitlines()[0],
        'cpu': args.cpu, 'init_marker_seen': seen, 'expected_page_rejection': args.expect_incompatible_pages,
        'stopped_after_page_rejection': stopped_after_rejection, 'qemu_timed_out': timed_out,
        'qemu_exit_code': code, 'passed': passed, 'kernel_booted_under_qemu': seen,
        'full_desktop_booted': False, 'installer_admission': False, 'hardware_validated': False}
    (output / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    if not passed:
        raise ValueError('kernel EFI fixture failed; inspect qemu.log')
    marker.unlink()
    print('Kernel EFI fixture passed; no native M4 or desktop qualification')


if __name__ == '__main__':
    main()
