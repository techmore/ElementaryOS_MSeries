#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exercise private Mesa retention with read-only /usr and initially empty /opt.

Requires an isolated, configured ARM64 candidate root and compiled
 test-mesa-software.c binary. Does not boot an image or test M4 hardware.
"""
import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--smoke', type=Path, required=True)
parser.add_argument('--id-map', choices=['auto', 'single'], default='auto',
                    help='single checks existing roots without subordinate-ID helper privileges')
args = parser.parse_args()
root = args.root.resolve()
if root == Path('/') or not (root / 'usr/lib/elementary-m4-gravity1/lib/libEGL_mesa.so.0').is_file():
    raise ValueError('isolated candidate root with persistent Mesa required')
with tempfile.TemporaryDirectory(prefix='m4-retention-', dir=root / 'tmp') as temp:
    binary = Path(temp) / 'mesa-software'
    shutil.copy2(args.smoke, binary)
    inside = '/' + str(binary.relative_to(root))
    hook = Path(temp) / 'activate-graphics.chroot'
    shutil.copy2(Path(__file__).resolve().parents[2] /
                 'mkosi.images/base/mkosi.profiles/m4-mini/activate-graphics.chroot', hook)
    inside_hook = '/' + str(hook.relative_to(root))
    script = r"""set -eu
mount -t tmpfs -o size=1M,nosuid tmpfs "$1/dev"
touch "$1/dev/null"
mount --bind /dev/null "$1/dev/null"
mount -t proc -o ro,nosuid,nodev,noexec proc "$1/proc"
mount -t tmpfs -o size=1M tmpfs "$1/opt"
mount --bind "$1/usr" "$1/usr"
mount -o remount,bind,ro "$1/usr"
# Refuse unexpected legacy data without deleting it.
chroot "$1" mkdir /opt/elementary-m4-gravity1
chroot "$1" touch /opt/elementary-m4-gravity1/keep-this
if chroot "$1" "$3"; then
    echo 'Nonempty legacy prefix was incorrectly accepted' >&2
    exit 1
fi
test -f "$1/opt/elementary-m4-gravity1/keep-this"
chroot "$1" rm /opt/elementary-m4-gravity1/keep-this
# Replay the real hook to cover dpkg's empty legacy directory upgrade case.
chroot "$1" "$3"
test "$(chroot "$1" readlink /opt/elementary-m4-gravity1)" = /usr/lib/elementary-m4-gravity1
chroot "$1" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C LIBGL_ALWAYS_SOFTWARE=1 MESA_SHADER_CACHE_DISABLE=true "$2"
chroot "$1" /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LC_ALL=C MESA_SHADER_CACHE_DISABLE=true /opt/elementary-m4-gravity1/bin/run-mesa --software -- "$2"
"""
    result = subprocess.run(['unshare', '--user', *(['--map-auto'] if args.id_map == 'auto' else []),
                             '--map-root-user', '--mount', '--pid', '--fork',
                             '/bin/sh', '-c', script, 'm4-retention', str(root), inside, inside_hook],
                   check=True, capture_output=True, text=True)
    print(result.stdout, end='')
    if result.stdout.count('Mesa 26.3.0-devel') != 2:
        raise ValueError('both ordinary and wrapper rendering must load the matched Mesa')
print('Read-only /usr and empty-/opt retention checks passed; no image boot or M4 hardware test')
