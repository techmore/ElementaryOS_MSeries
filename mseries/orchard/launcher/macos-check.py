#!/usr/bin/env python3
"""Read-only checks for the experimental VMApple research lane; never boot a VM."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

CHECKS = ('host', 'kvm', 'qemu', 'firmware', 'guest', 'qualification')


def check(name, directory, qemu):
    if name == 'host':
        return platform.system() == 'Linux' and platform.machine() == 'aarch64', platform.system() + ' / ' + platform.machine()
    if name == 'kvm':
        accessible = os.access('/dev/kvm', os.R_OK | os.W_OK)
        return accessible, '/dev/kvm accessible' if accessible else '/dev/kvm is unavailable to this user'
    if name == 'qemu':
        binary = shutil.which(qemu)
        if not binary:
            return False, 'QEMU executable not found; configure QEMU_VMAPPLE after building the research stack'
        try:
            result = subprocess.run([binary, '-machine', 'help'], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired) as error:
            return False, 'QEMU machine query failed: ' + str(error)
        found = result.returncode == 0 and any(line.split()[:1] == ['vmapple'] for line in result.stdout.splitlines())
        return found, 'VMApple machine available; kernel and guest compatibility remain unverified' if found else 'This QEMU has no vmapple machine; stock QEMU is not sufficient'
    if name == 'qualification':
        return False, 'Unqualified: M1 Pro/Aurora needs Apple KVM state patches, a real guest boot, iMessage activation, and save/restore tests'
    files = ['AVPBooter.vmapple2.bin'] if name == 'firmware' else ['disk.img', 'aux.img', 'vm.json']
    missing = [filename for filename in files if not (directory / filename).is_file() or (directory / filename).stat().st_size == 0]
    if missing:
        return False, 'Missing ' + ', '.join(missing) + ' in ' + str(directory)
    if name == 'guest':
        try:
            identity = json.loads((directory / 'vm.json').read_text())
            if not isinstance(identity, dict) or not identity:
                raise ValueError('expected a nonempty VM configuration object')
        except (OSError, ValueError) as error:
            return False, 'vm.json is unreadable or invalid: ' + str(error)
        return True, 'Disk, AUX and VM configuration present; their matching provenance and boot are not verified'
    return True, 'AVPBooter present; version compatibility is not verified'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', choices=CHECKS)
    parser.add_argument('--macos-dir', type=Path, default=Path(os.environ.get('MACOS_DIR', str(Path.home() / 'vms/macos'))))
    parser.add_argument('--qemu', default=os.environ.get('QEMU_VMAPPLE', 'qemu-system-aarch64'))
    args = parser.parse_args()
    results = []
    for name in (args.check,) if args.check else CHECKS:
        try:
            ok, detail = check(name, args.macos_dir, args.qemu)
        except OSError as error:
            ok, detail = False, str(error)
        results.append(ok)
        print(('PASS' if ok else 'NEEDS WORK') + ': ' + detail)
    return 0 if all(results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
