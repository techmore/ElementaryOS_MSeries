#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Run one command with the sibling private-prefix Mesa; no global activation."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--software', action='store_true', help='force llvmpipe; does not test M4 GPU')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command
    if command[:1] == ['--']:
        command = command[1:]
    if not command:
        parser.error('command required after --')
    prefix = Path(__file__).resolve().parent.parent
    vendor = prefix / 'share/glvnd/egl_vendor.d/50_mesa.json'
    icd = prefix / 'share/vulkan/icd.d/asahi_icd.aarch64.json'
    for path in [vendor, icd, prefix / 'lib/libvulkan_asahi.so', prefix / 'lib/libEGL_mesa.so.0']:
        if not path.is_file():
            parser.error('incomplete private Mesa prefix: ' + str(path))
    env = dict(os.environ)
    env['LD_LIBRARY_PATH'] = str(prefix / 'lib') + (':' + env['LD_LIBRARY_PATH'] if env.get('LD_LIBRARY_PATH') else '')
    env['__EGL_VENDOR_LIBRARY_FILENAMES'] = str(vendor)
    env['LIBGL_DRIVERS_PATH'] = str(prefix / 'lib/dri')
    debug = [value for value in env.get('ASAHI_MESA_DEBUG', '').split(',') if value]
    env['ASAHI_MESA_DEBUG'] = ','.join(dict.fromkeys(debug + ['nocompress']))
    if args.software:
        env['LIBGL_ALWAYS_SOFTWARE'] = '1'
    with tempfile.TemporaryDirectory(prefix='m4-mesa-icd-') as temp:
        manifest = json.loads(icd.read_text())
        manifest['ICD']['library_path'] = str(prefix / 'lib/libvulkan_asahi.so')
        selected_icd = Path(temp) / 'asahi.json'
        selected_icd.write_text(json.dumps(manifest))
        env['VK_DRIVER_FILES'] = str(selected_icd)
        env['VK_ICD_FILENAMES'] = str(selected_icd)
        result = subprocess.run(command, env=env)
    return result.returncode if result.returncode >= 0 else 128 - result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
