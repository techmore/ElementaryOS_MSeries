#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check a configured elementary candidate root; does not start its desktop."""
import argparse
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--receipt', type=Path, required=True)
args = parser.parse_args()
root = args.root.resolve()
if root == Path('/') or args.receipt.exists():
    raise ValueError('isolated root and new receipt required')


def inside(*command):
    return subprocess.check_output([
        'unshare', '--user', '--map-auto', '--map-root-user', '--mount', '--pid', '--fork',
        '/bin/sh', '-c', 'mount --bind /dev/null "$1/dev/null" && '
        'mount -t proc -o ro,nosuid,nodev,noexec proc "$1/proc" && '
        'shift && exec chroot "$@"', 'm4-desktop-check', str(root), str(root),
        '/usr/bin/env', '-i', 'PATH=/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL=C', *command],
        text=True, stderr=subprocess.STDOUT)


audit = inside('dpkg', '--audit')
if audit.strip():
    raise ValueError('unclean package audit: ' + audit)
inside('apt-get', 'check')
rows = inside('dpkg-query', '-W', '-f=${Package}\t${Version}\t${db:Status-Status}\n').splitlines()
packages = {name: version for name, version, status in (row.split('\t') for row in rows)
            if status == 'installed'}
required = {'elementary-desktop', 'elementary-minimal', 'elementary-standard',
            'casper', 'distinst', 'io.elementary.installer-session', 'gala', 'lightdm',
            'io.elementary.wingpanel', 'linux-image-elementary-m4-gravity1',
            'elementary-m4-gravity-mesa1', 'elementary-m4-gravity-policy'}
if not required <= packages.keys():
    raise ValueError('required desktop packages missing: ' + str(required - packages.keys()))
foreign = {'elementary-live', 'ubuntu-x13s-settings-nogrub', 'ubuntu-x1e-settings-nogrub'} & packages.keys()
if foreign:
    raise ValueError('foreign board live metapackage/hooks remain: ' + str(foreign))
libraries = {}
for binary in ['usr/bin/gala', 'usr/bin/io.elementary.wingpanel', 'usr/sbin/lightdm']:
    result = inside('ldd', '/' + binary)
    if 'not found' in result:
        raise ValueError('unresolved desktop library: ' + binary + '\n' + result)
    libraries['/' + binary] = 'all linked libraries resolved'
inside('glib-compile-schemas', '--strict', '--dry-run', '/usr/share/glib-2.0/schemas')
session = root / 'usr/share/wayland-sessions/pantheon-wayland.desktop'
if not session.is_file() or not (root / 'usr/share/gnome-session/sessions/pantheon-wayland.session').is_file():
    raise ValueError('Pantheon Wayland session missing')
args.receipt.write_text(json.dumps({
    'scope': 'configured desktop packages, linked libraries and schemas; no graphical session launch',
    'installed_package_count': len(packages), 'required_versions': {p: packages[p] for p in sorted(required)},
    'dpkg_audit': 'clean', 'apt_dependency_check': 'passed', 'desktop_libraries': libraries,
    'schemas': 'strict dry run passed', 'pantheon_wayland_session': 'present',
    'hardware_validated': False, 'graphical_login_tested': False, 'factory_image_built': False,
}, indent=2) + '\n')
print('Configured desktop package, dependency, linked-library, schema and session-file checks passed')
