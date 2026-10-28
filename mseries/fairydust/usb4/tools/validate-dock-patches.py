#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Validate the experimental patch stack in scratch space; never build/install a kernel.

Requires a C compiler, git, bison and flex. The archive is the same SHA-pinned
Fairydust source used by debian/build.sh. Builds its own float-capable dtc so no
GPU DT cells are changed to accommodate a stock compiler. E4 DTBs disable built-in
HDMI and are test artifacts, not fallback-qualified deployment candidates.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

PIN = 'ce9f2eba72c061a50b2d790450e90af3439d8c24'
ARCHIVE_SHA256 = '20ce358acffff4b3de86201975cd68c7aaf241ae010ec3cca9422bbe2b7f34aa'
KIT = Path(__file__).resolve().parent.parent


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def verify_archive(path, git_archive=False):
    """The codeload tarball must match ARCHIVE_SHA256. A `git archive` copy must carry the pinned commit id
    in its pax comment: git wrote it from a commit fetched by that full id, so git already checked the content."""
    if not git_archive:
        if sha(path) != ARCHIVE_SHA256:
            raise ValueError('kernel archive does not match the reviewed source pin')
        return {'archive_sha256': ARCHIVE_SHA256}
    with tarfile.open(path, 'r:gz') as archive:
        archive.next()  # reads the global pax header git archive writes first
        commit = archive.pax_headers.get('comment')
    if commit != PIN:
        raise ValueError(f'git archive is of {commit!r}, not the reviewed source pin {PIN}')
    return {'archive_git_commit': PIN}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True, help='fresh scratch directory')
    parser.add_argument('--git-archive', action='store_true',
                        help='the archive came from `git archive` of the pin fetched by its full commit id '
                             '(the CI fallback when codeload rate-limits); checked by the commit id git '
                             'embeds, since its bytes never match the codeload tarball')
    args = parser.parse_args()
    archive_check = verify_archive(args.archive, args.git_archive)
    output = args.output.resolve()
    # This tool only creates a new directory. It never overwrites an existing source/build tree.
    output.mkdir(parents=True, exist_ok=False)
    source = output/'source'
    source.mkdir()
    patches = []
    needed = set()
    for number in range(1, 16):
        choices = list(KIT.glob(f'{number:04d}-*.patch'))
        if len(choices) != 1:
            raise ValueError(f'expected one patch for {number:04d}')
        patches.append(choices[0])
        needed.update(re.findall(r'^--- a/([^\t\n]+)', choices[0].read_text(), re.M))
    # Extract regular selected files only; do not follow archive symlinks or trust member paths.
    with tarfile.open(args.archive, 'r:gz') as archive:
        for member in archive:
            prefix, _, name = member.name.partition('/')
            if prefix != 'linux-' + PIN or not member.isfile():
                continue
            path = Path(name)
            if path.is_absolute() or '..' in path.parts:
                raise ValueError('unsafe archive path')
            if name not in needed and not name.startswith(('arch/arm64/boot/dts/apple/', 'include/dt-bindings/', 'scripts/dtc/')):
                continue
            target = source/path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.extractfile(member).read())
    logfile = (output/'validation.log').open('w')
    def run(argv, cwd=source):
        result = subprocess.run([str(a) for a in argv], cwd=cwd, capture_output=True, text=True)
        logfile.write('$ ' + ' '.join(map(str, argv)) + '\n' + result.stdout + result.stderr)
        logfile.flush()
        if result.returncode:
            # Keep compiler/test errors visible in CI; its scratch directory is not retained.
            print((result.stdout + result.stderr)[-12000:], file=sys.stderr)
            raise RuntimeError(f'command failed ({result.returncode}); inspect {output / "validation.log"}: {argv[0]}')
        return result.stdout
    run(['git', 'init', '-q'])
    for patch in patches[:14]:
        run(['git', 'apply', '--check', patch])
        run(['git', 'apply', patch])
    cc = os.environ.get('CC', 'cc')
    dtc_dir = source/'scripts/dtc'
    run([os.environ.get('BISON', 'bison'), '-d', '-o', 'dtc-parser.tab.c', 'dtc-parser.y'], dtc_dir)
    run([os.environ.get('FLEX', 'flex'), '-o', 'dtc-lexer.lex.c', 'dtc-lexer.l'], dtc_dir)
    (dtc_dir/'version_gen.h').write_text('#define DTC_VERSION "pinned-fairydust-' + PIN[:8] + '"\n')
    objects = ['dtc', 'flattree', 'fstree', 'data', 'livetree', 'treesource', 'srcpos', 'checks', 'util', 'dtc-lexer.lex', 'dtc-parser.tab']
    run([cc, '-O2', '-DNO_YAML', '-I.', '-Ilibfdt', *[name+'.c' for name in objects], '-lm', '-o', 'dtc'], dtc_dir)
    def compile_board(board, label, delta=False):
        entry = source/'arch/arm64/boot/dts/apple'/(board+'.dts')
        if delta:
            entry = output/(label+'-input.dts')
            entry.write_text('#include "' + str(source/'arch/arm64/boot/dts/apple'/(board+'.dts')) + '"\n'
                             '#include "' + str(KIT/'e4-touchid-delta.dtsi') + '"\n')
        preprocessed = output/(label+'.dts')
        preprocessed.write_text(run([cc, '-E', '-nostdinc', '-Iinclude', '-Iarch/arm64/boot/dts/apple',
                                    '-undef', '-D__DTS__', '-x', 'assembler-with-cpp',
                                    entry]))
        binary = output/(label+'.dtb')
        run([dtc_dir/'dtc', '-I', 'dts', '-O', 'dtb', '-o', binary, preprocessed])
        return binary
    e3 = compile_board('t6000-j314s', 'e3-j314s')
    control_before = compile_board('t6001-j314c', 'e3-control-j314c')
    run([sys.executable, source/'tools/testing/apple-dpin/test-dtb.py', e3, control_before])
    # Execute actual production helper/functions against deterministic fake I/O, not a separate model.
    shims = output/'shims/linux'
    shims.mkdir(parents=True)
    # Linux glibc's errno.h already includes linux/errno.h; a shim there would recurse.
    # Only non-Linux hosts need this compatibility header for the userspace harness.
    if sys.platform != 'linux':
        (shims/'errno.h').write_text('#include <errno.h>\n')
    helper = output/'dpin-offline'
    run([cc, '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-fsanitize=undefined',
         '-I'+str(shims.parent), '-Idrivers/phy/apple', 'tools/testing/apple-dpin/dpin-offline.c', '-o', helper])
    contract_runs = {"helper": run([helper])}
    for name in ('clock', 'connection', 'bridge', 'lookup'):
        contract_runs[name] = run([sys.executable, source/f'tools/testing/apple-dpin/test-{name}.py', source])
    contract_runs['hpd'] = run([sys.executable, KIT/'tools/test-hpd-policy.py', source])
    run(['git', 'apply', '--check', patches[14]])
    run(['git', 'apply', patches[14]])
    e4 = compile_board('t6000-j314s', 'e4-j314s')
    control_after = compile_board('t6001-j314c', 'e4-control-j314c')
    touchid = compile_board('t6000-j314s', 'e4-touchid-j314s', delta=True)
    run([sys.executable, source/'tools/testing/apple-dpin/test-dtb.py', e4, control_after])
    spec = importlib.util.spec_from_file_location('boot_tree', KIT/'tools/prepare-dpin-boot.py')
    tree = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tree)
    for binary, address in ((e3, '28cc00000'), (e4, '289c00000')):
        _, nodes = tree.parse(binary.read_bytes())
        controller = nodes['/soc/dcp@'+address]
        nhi = nodes['/soc/cio@b01ac0000/nhi@f00000']
        if 'apple,dp-tunnel' not in controller or nhi['apple,dp-source'] != controller['phandle']:
            raise ValueError('compiled NHI source does not match selected experiment')
    if control_before.read_bytes() != control_after.read_bytes():
        raise ValueError('E4 changed the non-target control board')
    _, nodes = tree.parse(e4.read_bytes())
    if '/soc/dcp@289c00000/ports/port@1' in nodes or 'remote-endpoint' in nodes['/soc/phy@1303000000/ports/port@2/endpoint']:
        raise ValueError('E4 retained a built-in HDMI endpoint')
    _, touch_nodes = tree.parse(touchid.read_bytes())
    if touch_nodes['/soc/sep@396400000'].get('status') != b'okay\0' or touch_nodes['/soc/spi@39b108000/fingerprint@0'].get('compatible') != b'apple,mesa-fingerprint\0':
        raise ValueError('Touch ID delta missing expected nodes')
    normalized = tree.normalized(nodes)
    normalized_touch = tree.normalized(touch_nodes)
    for path in ('/soc/dcp@289c00000', '/soc/dcp@28cc00000', '/soc/cio@b01ac0000/nhi@f00000'):
        if normalized[path] != normalized_touch[path]:
            raise ValueError('Touch ID delta changed dock routing')
    groups = {name: sum(map(int, re.findall(r'PASS: (\d+) .*?groups', text))) for name,text in contract_runs.items()}
    if not all(groups.values()):
        raise ValueError('missing production test completion receipt')
    result = {'production_test_groups': groups, 'source_pin': PIN, **archive_check,
              'patches': {p.name: sha(p) for p in patches},
              'dtb_sha256': {p.name: sha(p) for p in (e3,e4,touchid,control_before,control_after)},
              'status': 'PASS: 0001-0015 apply; production helper/contracts and E3/E4 DT checks pass',
              'touchid_delta_preserves_dock_routing': True, 'non_target_board_unchanged': True, 'full_kernel_or_module_build': False,
              'hardware_boot_or_dock_picture_verified': False}
    (output/'validation.json').write_text(json.dumps(result,indent=2)+'\n')
    logfile.close()
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
