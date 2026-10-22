#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare external/2D compiler output with dynamic inputs and rejection controls."""
import argparse
import hashlib
import json
import re
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mesa-workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--native-object', type=Path)
    parser.add_argument('--source-sha256')
    parser.add_argument('--expect-uncorrected', action='store_true')
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        raise ValueError('new output required')
    mesa = args.mesa_workspace.resolve()
    source = mesa / 'mesa-87ac51d411f0e58a9433567ec2666f457be89e1d'
    build = mesa / 'build'
    native_source = source / 'src/asahi/compiler/agx_compile_apple9.c'
    if args.native_object:
        native = args.native_object.absolute()
    else:
        native = build / 'src/asahi/compiler/libasahi_compiler.a.p/agx_compile_apple9.c.o'
        if not args.source_sha256:
            raise ValueError('built-library mode requires an expected native source hash')
    if not native.is_file() or native.is_symlink():
        raise ValueError('regular native object required')
    if args.source_sha256 and hashlib.sha256(native_source.read_bytes()).hexdigest() != args.source_sha256:
        raise ValueError('native compiler source hash mismatch')
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
    link[1:1] = [str(obj)] + ([str(native)] if args.native_object else [])
    with (root / 'link.log').open('wb') as log:
        subprocess.run(link, cwd=build, stdout=log, stderr=subprocess.STDOUT, check=True)
    run = [str(root / 'review')] + (['--expect-uncorrected'] if args.expect_uncorrected else [])
    result = subprocess.run(run, capture_output=True, text=True)
    (root / 'result.log').write_text(result.stdout + result.stderr)
    match = re.search(r'RESULT positive=(\d+) negative=(\d+) original_rejections=(\d+) passed=(\d+)', result.stdout)
    if result.returncode or not match:
        raise ValueError('external sampler matrix failed; inspect result.log')
    positive, negative, rejected, passed = map(int, match.groups())
    if negative != 4 or passed != 1 or (rejected < 1 if args.expect_uncorrected else positive != 24):
        raise ValueError('external sampler case coverage incomplete')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    record = {
        'scope': '24 constant/dynamic external/2D binary and binding-mask comparisons across direct/sampler-state paths, plus four invalid external array/shadow controls; no GPU',
        'positive_comparisons': positive, 'rejection_controls': negative,
        'uncorrected_rejections': rejected, 'expect_uncorrected': args.expect_uncorrected,
        'separate_native_object': bool(args.native_object),
        'expected_native_source_sha256': args.source_sha256,
        'cases': ['nearest', 'linear', 'bias', 'projective', 'texel_fetch', 'size_query'],
        'all_compiler_byte_comparisons_passed': positive == 24,
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
    print('Compiler matrix and rejection controls pass; this is not extension conformance')


if __name__ == '__main__':
    main()
