#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Check a configured elementary candidate root; does not start its desktop."""
import argparse
import os
import json
from pathlib import Path
import subprocess

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, required=True)
parser.add_argument('--receipt', type=Path, required=True)
parser.add_argument('--kind', choices=['research-live', 'factory-base'], default='research-live')
parser.add_argument('--id-map', choices=['auto', 'single', 'host-root'], default='auto',
                    help='single checks existing roots without subordinate-ID helper privileges')
args = parser.parse_args()
if args.id_map == 'host-root' and (os.geteuid() != 0 or os.environ.get('GITHUB_ACTIONS') != 'true'):
    raise ValueError('host-root inspection requires root on the explicit GitHub runner')
root = args.root.resolve()
if root == Path('/') or args.receipt.exists():
    raise ValueError('isolated root and new receipt required')


def inside(*command):
    return subprocess.check_output([
        'unshare', *([] if args.id_map == 'host-root' else ['--user', *(['--map-auto'] if args.id_map == 'auto' else []), '--map-root-user']), '--mount', '--pid', '--fork',
        '/bin/sh', '-c', 'mount -t tmpfs -o size=1M,nosuid tmpfs "$1/dev" && '
        'touch "$1/dev/null" && mount --bind /dev/null "$1/dev/null" && '
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
            'gala', 'lightdm',
            'io.elementary.wingpanel', 'linux-image-elementary-m4-gravity1',
            'elementary-m4-gravity-mesa1', 'elementary-m4-gravity-policy'}
if args.kind == 'research-live':
    required |= {'casper', 'distinst'}
if not required <= packages.keys():
    raise ValueError('required desktop packages missing: ' + str(required - packages.keys()))
foreign = {'elementary-live', 'io.elementary.installer', 'io.elementary.installer-session',
           'ubuntu-x13s-settings-nogrub', 'ubuntu-x1e-settings-nogrub'} & packages.keys()
if foreign:
    raise ValueError('foreign board live metapackage/hooks remain: ' + str(foreign))
for path in ['usr/bin/io.elementary.installer', 'usr/share/wayland-sessions/installer.desktop',
             'usr/lib/systemd/user/io.elementary.installer.service']:
    if (root / path).exists() or (root / path).is_symlink():
        raise ValueError('graphical installer entry remains: ' + path)
lightdm = inside('lightdm', '--show-config')
for setting in (['user-session=pantheon-wayland', 'autologin-session=pantheon-wayland']
                if args.kind == 'research-live' else []):
    if setting not in lightdm:
        raise ValueError('missing effective LightDM setting: ' + setting)
if 'user-session=installer' in lightdm:
    raise ValueError('installer session is still selected')
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
    'namespace_id_map': args.id_map,
    'scope': args.kind + ': configured packages, linked libraries and schemas; no graphical session launch',
    'installed_package_count': len(packages), 'required_versions': {p: packages[p] for p in sorted(required)},
    'dpkg_audit': 'clean', 'apt_dependency_check': 'passed', 'desktop_libraries': libraries,
    'schemas': 'strict dry run passed', 'lightdm_session': ('Pantheon Wayland for login and autologin' if args.kind == 'research-live'
                                                         else 'installer session not selected; live autologin not asserted'),
    'graphical_installer_packages': 'absent', 'pantheon_wayland_session': 'present',
    'hardware_validated': False, 'graphical_login_tested': False, 'factory_image_built': False,
}, indent=2) + '\n')
print('Configured desktop package, dependency, linked-library, schema and session-file checks passed')
