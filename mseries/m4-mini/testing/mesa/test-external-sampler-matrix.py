#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare six external/2D operations using an explicitly supplied candidate object."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-object', type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        raise ValueError('new output required')
    mesa = args.mesa_workspace.resolve()
    source = mesa / 'mesa-87ac51d411f0e58a9433567ec2666f457be89e1d'
    build = mesa / 'build'
    native = args.native_object.resolve()
    if not native.is_file() or native.is_symlink():
        raise ValueError('regular candidate native object required')
    root.mkdir(parents=True)
    marker = root / 'INCOMPLETE'
    marker.touch()
    fixture = Path(__file__).with_name('external-sampler-matrix.cpp').resolve()
    items = json.loads((build / 'compile_commands.json').read_text())
    item = next(c for c in items if c['file'].endswith('/test/test-apple9.cpp'))
    command = shlex.split(item['command']) if 'command' in item else item['arguments']
    obj = root / 'review.o'
    command[command.index('-o') + 1] = str(obj)
    command[command.index('-c') + 1] = str(fixture)
    for option, value in [('-MF', str(obj) + '.d'), ('-MQ', str(obj))]:
        if option in command:
            command[command.index(option) + 1] = value
    with (root / 'compile.log').open('wb') as log:
        subprocess.run(command, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
    recipe = subprocess.check_output(['ninja', '-C', str(build), '-t', 'commands',
                                     'src/asahi/compiler/agx_tests'], text=True).splitlines()[-1]
    link = [a for a in shlex.split(recipe) if not a.endswith('.o') and
            a != 'src/gtest/libgtest.a' and a not in ['-Wl,--whole-archive', '-Wl,--no-whole-archive']]
    link[link.index('-o') + 1] = str(root / 'review')
    link[1:1] = [str(obj), str(native)]
    with (root / 'link.log').open('wb') as log:
        subprocess.run(link, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
    result = subprocess.run([str(root / 'review')], capture_output=True, text=True, check=True)
    (root / 'result.log').write_text(result.stdout + result.stderr)
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    record = {
        'scope': 'six matching external/2D compiler byte comparisons; explicitly supplied native object; no EGL/DRM/GPU device',
        'cases': ['nearest', 'linear', 'bias', 'projective', 'texel_fetch', 'size_query'],
        'all_compiler_byte_comparisons_passed': True,
        'fixture_sha256': sha(fixture), 'runner_sha256': sha(Path(__file__)),
        'native_object_sha256': sha(native),
        'source_files': {n: sha(source / n) for n in ['src/asahi/compiler/agx_compile_apple9.c',
            'src/gallium/drivers/asahi/agx_pipe.c', 'src/mesa/state_tracker/st_extensions.c',
            'src/mesa/main/extensions.c', 'src/mesa/main/teximage.c']},
        'compile_command': command, 'link_command': link, 'result': result.stdout,
        'hardware_validated': False, 'native_render_failure_reproduced': False}
    (root / 'receipt.json').write_text(json.dumps(record, indent=2) + '\n')
    marker.unlink()
    print(result.stdout, end='')
    print('Six compiler comparisons pass; this is not extension conformance')


if __name__ == '__main__':
    main()
