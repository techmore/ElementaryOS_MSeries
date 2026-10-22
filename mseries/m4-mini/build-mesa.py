#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build and stage pinned Gravity Mesa in isolation; never alter system libraries."""
import argparse
import hashlib
import json
import os
import shlex
from pathlib import Path
import subprocess
import tarfile

COMMIT = '87ac51d411f0e58a9433567ec2666f457be89e1d'
SHA256 = '1195f212bcf5816b8b893113b0b5dc578ce744d420856b6ad4f42008889e231e'
UAPI_SHA256 = 'eb9f39e87dfe448dc044f54ab2d11b7493bf1359faca8fb76ece5f3583469015'
OPTIONS = ['--prefix=/opt/elementary-m4-gravity1', '--libdir=lib',
           '-Dplatforms=x11,wayland', '-Dgallium-drivers=asahi,llvmpipe',
           '-Dvulkan-drivers=asahi', '-Dllvm=enabled', '-Dbuild-tests=true']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--jobs', type=int, default=2)
    parser.add_argument('--pkg-config-path', help='optional work-local build dependencies')
    args = parser.parse_args()
    with args.archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != SHA256:
            raise ValueError('Mesa source archive checksum mismatch')
    if args.output.exists() or args.jobs < 1:
        raise ValueError('new output and positive jobs required')
    root = args.output.resolve()
    root.mkdir(parents=True)
    with tarfile.open(args.archive) as archive:
        if any(Path(member.name).parts[0] != 'mesa-' + COMMIT for member in archive):
            raise ValueError('unexpected Mesa source root')
        archive.extractall(root, filter='data')
    source, build = root / ('mesa-' + COMMIT), root / 'build'
    if hashlib.sha256((source / 'include/drm-uapi/asahi_drm.h').read_bytes()).hexdigest() != UAPI_SHA256:
        raise ValueError('matched Gravity kernel/Mesa DRM UAPI required')
    env = dict(os.environ)
    if args.pkg_config_path:
        env['PKG_CONFIG_PATH'] = args.pkg_config_path
    commands = [
        ['meson', 'setup', str(build), str(source)] + OPTIONS,
        ['meson', 'compile', '-C', str(build), '-j', str(args.jobs)],
        ['meson', 'test', '-C', str(build), '--no-rebuild', '--print-errorlogs', 'agx_tests', 'agx_apple9_launcher_tests', 'agx_apple9_geometry_tests',
         'agx2_disasm', 'agx2_python_disasm'],
        ['meson', 'install', '-C', str(build), '--no-rebuild', '--destdir', str(root / 'stage')],
    ]
    for index, command in enumerate(commands):
        with (root / f'{index}.log').open('wb') as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    flags = shlex.split(subprocess.check_output(['pkg-config', '--cflags', '--libs', 'egl', 'gl'], env=env, text=True))
    smoke = root / 'mesa-software'
    subprocess.run(['cc', '-Wall', '-Wextra', '-Werror',
                    str(Path(__file__).parent / 'test-mesa-software.c'), '-o', str(smoke)] + flags,
                   env=env, check=True)
    prefix = root / 'stage/opt/elementary-m4-gravity1'
    smoke_env = dict(env, LD_LIBRARY_PATH=str(prefix / 'lib'),
                     __EGL_VENDOR_LIBRARY_FILENAMES=str(prefix / 'share/glvnd/egl_vendor.d/50_mesa.json'),
                     LIBGL_DRIVERS_PATH=str(prefix / 'lib/dri'), LIBGL_ALWAYS_SOFTWARE='1',
                     MESA_SHADER_CACHE_DIR=str(root / 'shader-cache'))
    with (root / 'software-smoke.log').open('wb') as log:
        subprocess.run([str(smoke)], env=smoke_env, stdout=log, stderr=subprocess.STDOUT, check=True)
    test_results = [json.loads(line) for line in (build / 'meson-logs/testlog.json').read_text().splitlines() if line.strip()]
    if len(test_results) != 5 or any(test['result'] != 'OK' for test in test_results):
        raise ValueError('all five selected AGX test groups must pass')
    libraries = ['lib/libvulkan_asahi.so', 'lib/libgallium-26.3.0-devel.so',
                 'lib/libEGL_mesa.so.0.0.0', 'lib/libGLX_mesa.so.0.0.0']
    artifacts = {name: hashlib.sha256((prefix / name).read_bytes()).hexdigest() for name in libraries}
    (root / 'receipt.json').write_text(json.dumps({
        'repository': 'GravityLinux/mesa', 'commit': COMMIT, 'archive_sha256': SHA256,
        'uapi_sha256': UAPI_SHA256, 'options': OPTIONS, 'commands': commands, 'build': 'passed',
        'tests': {'meson_groups': len(test_results), 'failed_groups': 0}, 'artifacts': artifacts,
        'status': 'built, AGX tests and isolated software rendering passed, staged only; no M4 GPU runtime qualification',
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
