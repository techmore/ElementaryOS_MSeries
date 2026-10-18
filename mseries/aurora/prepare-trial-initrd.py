#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retain a working Arch unlock userspace and replace its modules offline."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('newc', HERE.parent / 'fairydust/usb4/tools/repack-dpin-initramfs.py')
newc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(newc)


def split_image(image):
    """Preserve the complete early CPIO and padding before the main gzip."""
    if image.startswith(b'\x1f\x8b'):
        return b'', image
    pos = 0
    while image[pos:pos + 6] == b'070701':
        if pos + 110 > len(image):
            raise ValueError('truncated early archive')
        values = [int(image[pos + 6 + i * 8:pos + 14 + i * 8], 16) for i in range(13)]
        begin = pos + 110
        end = begin + values[11]
        if not values[11] or end > len(image) or image[end - 1] != 0:
            raise ValueError('invalid early archive name')
        name = image[begin:end - 1]
        pos = ((end + 3) & ~3) + values[6]
        pos = (pos + 3) & ~3
        if pos > len(image):
            raise ValueError('truncated early archive data')
        if name == b'TRAILER!!!':
            newc.parse(image[:pos])
            while pos < len(image) and image[pos] == 0:
                pos += 1
            if image[pos:pos + 2] != b'\x1f\x8b':
                raise ValueError('expected a gzip main archive after early CPIO')
            return image[:pos], image[pos:]
    raise ValueError('unsupported initramfs; expected early newc plus gzip')


def prepare(baseline, module_root, old_version, new_version, output, report):
    if output.exists() or report.exists():
        raise ValueError('choose new output/report paths')
    module_root = module_root.resolve()
    source = module_root / 'lib/modules' / new_version
    if not source.is_dir() or new_version == old_version:
        raise ValueError('missing distinct candidate module tree')
    image = baseline.read_bytes()
    prefix, compressed = split_image(image)
    rows, trailer = newc.parse(gzip.decompress(compressed))
    old_prefix = f'usr/lib/modules/{old_version}'
    selected = {newc.canonical(n)[len(old_prefix) + 1:] for n, v, d in rows
                if newc.canonical(n).startswith(old_prefix + '/kernel/') and stat.S_ISREG(v[1])}
    if not selected:
        raise ValueError('baseline has no selected modules')
    # Resolve the complete new dependency closure without inserting any module.
    for relative in list(selected):
        target = source / relative
        if not target.is_file():
            raise ValueError(f'candidate is missing baseline module {relative}')
        dependencies = subprocess.check_output(['modprobe', '--show-depends', '-d', str(module_root), '-S', new_version, str(target)], text=True)
        for line in dependencies.splitlines():
            parts = shlex.split(line)
            if parts and parts[0] == 'insmod':
                selected.add(str(Path(parts[1]).resolve().relative_to(source)))
    with tempfile.TemporaryDirectory(prefix='trial-initrd-') as temporary:
        root = Path(temporary)
        tree = root / 'usr/lib/modules' / new_version
        tree.mkdir(parents=True)
        (root / 'lib').symlink_to('usr/lib')
        for relative in sorted(selected):
            target = source / relative
            vermagic = subprocess.check_output(['modinfo', '-F', 'vermagic', str(target)], text=True).split()[0]
            if vermagic != new_version:
                raise ValueError(f'wrong module vermagic: {relative}')
            dest = tree / relative
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
        for path in source.glob('modules.builtin*'):
            shutil.copy2(path, tree / path.name)
        shutil.copy2(source / 'modules.order', tree / 'modules.order')
        subprocess.run(['depmod', '-b', str(root), new_version], check=True)
        retained = [(n, v, d) for n, v, d in rows if newc.canonical(n) != old_prefix and not newc.canonical(n).startswith(old_prefix + '/') and newc.canonical(n) != 'modlist.txt']
        ino = max(v[0] for n, v, d in rows) + 1
        for path in [tree, *sorted(tree.rglob('*'))]:
            mode = stat.S_IFDIR | 0o755 if path.is_dir() else stat.S_IFREG | 0o644
            data = b'' if path.is_dir() else path.read_bytes()
            values = [ino, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, 0, 0]
            retained.append((str(path.relative_to(root)), values, data)); ino += 1
        data = ('\n'.join(sorted(selected)) + '\n').encode()
        retained.append(('modlist.txt', [ino, stat.S_IFREG | 0o644, 0, 0, 1, 0, len(data), 0, 0, 0, 0, 0, 0], data))
        encoded = newc.encode(retained, trailer)
        verified, _ = newc.parse(encoded)
        after = {newc.canonical(n): (v, d) for n, v, d in verified}
        for name, values, data in rows:
            key = newc.canonical(name)
            if key != old_prefix and not key.startswith(old_prefix + '/') and key != 'modlist.txt':
                if after[key] != (values, data):
                    raise ValueError(f'unrelated unlock/userspace entry changed: {key}')
        required = ['hooks/encrypt', 'init', 'config', 'usr/bin/cryptsetup']
        if not all(p in after for p in required) or b'encrypt' not in after['config'][1]:
            raise ValueError('working encrypted-root unlock userspace is incomplete')
        result = prefix + gzip.compress(encoded, compresslevel=6, mtime=0)
        with output.open('xb') as stream:
            stream.write(result)
    receipt = {'schema': 1, 'kind': 'offline-initramfs-preparation', 'old_kernel': old_version, 'candidate_kernel': new_version,
               'baseline_sha256': hashlib.sha256(image).hexdigest(), 'candidate_sha256': hashlib.sha256(result).hexdigest(),
               'early_prefix_bytes': len(prefix), 'early_prefix_unchanged': result[:len(prefix)] == prefix,
               'nonmodule_userspace_and_unlock_entries_unchanged': True, 'selected_modules': sorted(selected),
               'module_count': len(selected), 'status': 'prepared offline; no boot or root-unlock qualification'}
    with report.open('x') as stream:
        stream.write(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps({k: receipt[k] for k in ('status', 'module_count', 'candidate_sha256')}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline', 'module-root', 'output', 'report'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--old-version', required=True)
    parser.add_argument('--new-version', required=True)
    args = parser.parse_args()
    prepare(args.baseline, args.module_root, args.old_version, args.new_version, args.output, args.report)
