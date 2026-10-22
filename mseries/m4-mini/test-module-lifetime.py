#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build a synthetic module/initramfs and test it ONLY inside diskless QEMU.

Requires an already built generic ARM64 module-enabled fixture kernel. Never
loads a module on the host. This exercises C scheduler module ownership, not
M4 GPU firmware, Rust driver unload or graphical/file-operation lifetime.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import struct

HERE = Path(__file__).resolve().parent


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path)
    parser.add_argument('--kernel-build', required=True, type=Path)
    parser.add_argument('--busybox', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--negative-owner', action='store_true', help='omit module identity; expect safe refusal before unload')
    args = parser.parse_args()
    source, build, busybox = args.source.resolve(), args.kernel_build.resolve(), args.busybox.resolve()
    if any(character.isspace() for path in [source, build, busybox, args.output.resolve()] for character in str(path)):
        raise ValueError('kernel/initramfs paths must not contain whitespace')
    if args.output.exists() or (build / 'source').resolve() != source:
        raise ValueError('new output and matching kernel source/build required')
    config = dict(line.split('=', 1) for line in (build / '.config').read_text().splitlines()
                  if line.startswith('CONFIG_') and '=' in line)
    for name in ['CONFIG_MODULES', 'CONFIG_MODULE_UNLOAD', 'CONFIG_DRM_SCHED', 'CONFIG_BLK_DEV_INITRD']:
        if config.get(name) != 'y':
            raise ValueError('fixture kernel requires ' + name + '=y')
    expected = json.loads((HERE / 'gravity/compatibility/resulting-files.json').read_text())
    sources = ['drivers/gpu/drm/scheduler/sched_main.c', 'drivers/gpu/drm/scheduler/sched_entity.c', 'include/drm/gpu_scheduler.h']
    hashes = {name: digest(source / name) for name in sources}
    if any(hashes[name] != expected[name] for name in sources):
        raise ValueError('reviewed current scheduler C source required')
    header = busybox.read_bytes()[:64]
    if header[:6] != b'\x7fELF\x02\x01' or struct.unpack_from('<H', header, 18)[0] != 183:
        raise ValueError('ARM64 little-endian BusyBox required')
    program_headers = subprocess.check_output(['readelf', '-l', str(busybox)], text=True)
    if 'INTERP' in program_headers:
        raise ValueError('static BusyBox required')
    args.output.mkdir(parents=True)
    root = args.output.resolve()
    marker = root / 'INCOMPLETE'
    marker.touch()
    fixture = HERE / 'testing/module-lifetime'
    module = root / 'module'
    module.mkdir()
    for name in ['Makefile', 'm4_sched_module_test.c']:
        shutil.copyfile(fixture / name, module / name)
    c_source = module / 'm4_sched_module_test.c'
    if args.negative_owner:
        text = c_source.read_text()
        if text.count('.owner = THIS_MODULE,') != 1:
            raise ValueError('negative control requires exact module owner initializer')
        c_source.write_text(text.replace('.owner = THIS_MODULE,', '.owner = NULL,'))
    shutil.copyfile(fixture / 'init', root / 'init')
    with (root / 'module-build.log').open('wb') as log:
        subprocess.run(['make', '-C', str(source), 'O=' + str(build), 'ARCH=arm64', 'CC=clang',
                        'LD=ld', 'HOSTCC=clang', '-j2', 'M=' + str(module), 'modules'],
                       check=True, stdout=log, stderr=subprocess.STDOUT)
    items = ['dir /bin 0755 0 0', 'dir /dev 0755 0 0', 'dir /proc 0755 0 0',
             'dir /sys 0755 0 0', 'dir /tmp 01777 0 0', 'nod /dev/console 0600 0 0 c 5 1',
             'nod /dev/null 0666 0 0 c 1 3', f'file /bin/busybox {busybox} 0755 0 0',
             'slink /bin/sh busybox 0777 0 0', f'file /init {root}/init 0755 0 0',
             f'file /m4_sched_module_test.ko {module}/m4_sched_module_test.ko 0644 0 0']
    (root / 'initramfs.list').write_text('\n'.join(items) + '\n')
    with (root / 'initramfs.cpio').open('wb') as output:
        subprocess.run([str(build / 'usr/gen_init_cpio'), str(root / 'initramfs.list')], check=True, stdout=output)
    command = ['qemu-system-aarch64', '-nodefaults', '-m', '1024', '-kernel', str(build / 'arch/arm64/boot/Image'),
               '-initrd', str(root / 'initramfs.cpio'), '-append', 'console=ttyAMA0 rdinit=/init kunit.enable=0 panic=-1',
               '-no-reboot', '-nographic', '-accel', 'tcg', '-serial', 'stdio', '-machine', 'virt', '-cpu', 'max',
               '-smp', '2', '-net', 'none']
    (root / 'command.json').write_text(json.dumps(command, indent=2) + '\n')
    try:
        with (root / 'run.log').open('wb') as log:
            result = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        status = {'exit': result.returncode, 'timed_out': False}
    except subprocess.TimeoutExpired:
        status = {'exit': None, 'timed_out': True}
    log = (root / 'run.log').read_text(errors='replace')
    tail = log.split('M4_SCHED_MODULE_TEST_BEGIN', 1)[-1]
    clean = not any(word in tail for word in ['WARNING:', 'kernel BUG', 'Oops:', 'BUG:'])
    passed = (status['exit'] == 0 and clean and 'M4_SCHED_MODULE_TEST_PASS' in log
              and 'M4_SCHED_MODULE_BUSY_AS_EXPECTED' in log and 'M4_SCHED_MODULE_EXIT' in log
              and 'M4_SCHED_MODULE_TEST_FAIL' not in log)
    negative = (args.negative_owner and status['exit'] == 0 and clean
                and 'M4_SCHED_MODULE_TEST_FAIL:callback_module_not_pinned' in log
                and 'M4_SCHED_MODULE_BUSY_AS_EXPECTED' not in log and 'M4_SCHED_MODULE_EXIT' not in log)
    record = {
        'scope': 'generic ARM64 QEMU TCG C scheduler/loadable backend module lifetime; not M4 GPU or Rust driver unload',
        'negative_owner': args.negative_owner, 'status': status, 'passed': passed,
        'expected_negative_failure_observed': bool(negative), 'clean_guest_after_begin': clean,
        'markers': [line for line in log.splitlines() if 'M4_SCHED_MODULE_' in line],
        'source_c_sha256': hashes, 'kernel_sha256': digest(build / 'arch/arm64/boot/Image'),
        'kernel_config_sha256': digest(build / '.config'), 'module_sha256': digest(module / 'm4_sched_module_test.ko'),
        'module_source_sha256': digest(c_source), 'init_sha256': digest(root / 'init'),
        'initramfs_sha256': digest(root / 'initramfs.cpio'), 'busybox_sha256': digest(busybox),
        'accelerator': 'tcg only; explicit direct command without fallback',
        'host_module_loaded': False, 'hardware_validated': False,
    }
    (root / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    if not (negative if args.negative_owner else passed):
        raise ValueError('fixture did not reach expected result; inspect run.log')
    marker.unlink()
    print('Expected missing-owner failure observed safely' if args.negative_owner else 'Deferred callback pins module; unload succeeds after cleanup')


if __name__ == '__main__':
    main()
