#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Build the complete M4 mkosi graph in a disposable source clone.

Consumes trusted prepare-image-inputs.py output and the verified research boot
bundle. Summary-only resolves the actual graph without building. Full execution
uses proper subordinate IDs or explicit hosted root; it never substitutes a
single-ID build.
ISO assembly, installation and native hardware acceptance are separate gates.
"""
import argparse
import hashlib
import difflib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location('image_inputs', HERE / 'prepare-image-inputs.py')
inputs_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs_module)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()



BOOT_HOOK = 'mkosi.images/sysupdate/mkosi.profiles/m4-mini/verify-boot-chain.chroot'


def fresh_boot_hash(receipt, sources, expected_dtb):
    required = {key: sources[name]['commit'] for key, name in
                [('bootloader', 'bootloader'), ('uboot', 'u-boot'), ('kernel', 'linux')]}
    if (not receipt.get('trusted_fresh_build_receipts') or receipt.get('source_commits') != required
            or receipt.get('configuration') != 'NO_DISPLAY; no appended config overrides'
            or receipt['inputs']['dtb']['sha256'] != expected_dtb):
        raise ValueError('trusted fresh boot assembly must retain pinned source/board/configuration')
    value = receipt['boot_bin_sha256']
    if not re.fullmatch(r'[0-9a-f]{64}', value):
        raise ValueError('invalid candidate boot hash')
    return value


def boot_hash_patch(original, baseline, candidate):
    if not all(re.fullmatch(r'[0-9a-f]{64}', value) for value in [baseline, candidate]):
        raise ValueError('full boot hashes required')
    if original.count(baseline) != 1:
        raise ValueError('boot hook differs from reviewed reference')
    changed = original.replace(baseline, candidate)
    return ''.join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                       fromfile='a/' + BOOT_HOOK, tofile='b/' + BOOT_HOOK))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--boot-bundle', type=Path, required=True)
    parser.add_argument('--boot-bundle-receipt', type=Path, help='trusted fresh assembly receipt from a verified hosted build')
    parser.add_argument('--mkosi-source', type=Path, required=True)
    parser.add_argument('--image-version', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--summary-only', action='store_true')
    parser.add_argument('--hosted-root', action='store_true', help='explicit root execution on an ephemeral GitHub runner')
    args = parser.parse_args()
    if args.hosted_root and (os.geteuid() != 0 or os.environ.get('GITHUB_ACTIONS') != 'true'):
        raise ValueError('hosted-root mode requires root on the explicit GitHub runner')
    if not re.fullmatch(r'[0-9]{14}', args.image_version):
        raise ValueError('explicit 14-digit research image version required')
    output = args.output.resolve()
    if output.exists() or output.is_relative_to(REPO):
        raise ValueError('new workspace outside the source checkout required')
    inputs = args.inputs.resolve()
    candidate = json.loads((inputs / 'candidate.json').read_text())
    if (inputs / 'INCOMPLETE').exists() or candidate['schema'] != 1:
        raise ValueError('complete prepared input workspace required')
    if candidate['preparer_sha256'] != digest(HERE / 'prepare-image-inputs.py'):
        raise ValueError('inputs must use the current reviewed preparer')
    if set(candidate['components']) != {'kernel', 'mesa', 'policy'}:
        raise ValueError('complete three-component input set required')
    for component in candidate['components'].values():
        name = component['file']
        if Path(name).name != name or not name.endswith('.deb'):
            raise ValueError('invalid component filename')
        if digest(inputs / 'packages' / name) != component['sha256']:
            raise ValueError('prepared component changed')
    for name, expected in inputs_module.SOURCE_ARCHIVES.values():
        if digest(inputs / name) != expected:
            raise ValueError('required corresponding source changed')
    additional_sources = {}
    for kind, component in candidate['components'].items():
        for name, expected in component.get('additional_source_archives', {}).items():
            if (kind != 'mesa' or name != 'gravity-mesa-compatibility-source.tar.gz' or
                    name in additional_sources or digest(inputs / name) != expected):
                raise ValueError('invalid additional corresponding source')
            additional_sources[name] = expected
    expected_boot = json.loads((HERE / 'receipts/2026-10-21-repeatable-boot-chain.json').read_text())['boot_bin_sha256']
    baseline_boot = expected_boot
    if args.boot_bundle_receipt:
        receipt = json.loads(args.boot_bundle_receipt.read_text())
        sources = json.loads((HERE / 'research.json').read_text())['gravity_stack']
        kernel_pin = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
        expected_boot = fresh_boot_hash(receipt, sources, kernel_pin['artifacts']['arch/arm64/boot/dts/apple/t8132-j773g.dtb'])
    if digest(args.boot_bundle) != expected_boot:
        raise ValueError('verified J773g boot bundle required')
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip()
    subprocess.run(['git', 'merge-base', '--is-ancestor', candidate['recipe_commit'], revision], cwd=REPO, check=True)
    baseline = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
    build = json.loads((inputs / 'records/kernel-build.json').read_text())
    original = subprocess.check_output(['git', 'show', revision + ':' + inputs_module.HOOK],
                                       cwd=REPO, text=True)
    patch = inputs_module.live_hook_patch(original, baseline, build)
    if (inputs / 'candidate-live-kernel.patch').read_text() != patch or digest(inputs / 'candidate-live-kernel.patch') != candidate['live_hook_patch_sha256']:
        raise ValueError('only the reviewed candidate kernel hash patch is permitted')
    boot_original = subprocess.check_output(['git', 'show', revision + ':' + BOOT_HOOK], cwd=REPO, text=True)
    boot_patch = boot_hash_patch(boot_original, baseline_boot, expected_boot)
    if not args.summary_only and not args.hosted_root:
        # Fail before creating a workspace if correct package ownership cannot
        # be represented. No privilege or UID-mapping fallback is attempted.
        subprocess.run(['unshare', '--user', '--map-auto', '--map-root-user', 'true'], check=True)
    output.mkdir(parents=True)
    marker = output / 'INCOMPLETE'
    marker.touch()
    source = output / 'source'
    subprocess.run(['git', 'clone', '--shared', '--no-checkout', str(REPO), str(source)], check=True)
    subprocess.run(['git', 'checkout', '--detach', revision], cwd=source, check=True)
    packages = output / 'packages'
    packages.mkdir()
    for component in candidate['components'].values():
        name = component['file']
        shutil.copy2(inputs / 'packages' / name, packages / name)
        if digest(packages / name) != component['sha256']:
            raise ValueError('copied component hash mismatch')
    for name in inputs_module.SOURCE_ARCHIVES:
        archive, expected = inputs_module.SOURCE_ARCHIVES[name]
        shutil.copy2(inputs / archive, output / archive)
        if digest(output / archive) != expected:
            raise ValueError('copied corresponding source mismatch')
    for archive, expected in additional_sources.items():
        shutil.copy2(inputs / archive, output / archive)
        if digest(output / archive) != expected:
            raise ValueError('copied additional corresponding source mismatch')
    shutil.copytree(inputs / 'records', output / 'input-records')
    shutil.copy2(inputs / 'candidate.json', output / 'input-candidate.json')
    if patch:
        subprocess.run(['git', 'apply', '--check', '-'], cwd=source, input=patch, text=True, check=True)
        subprocess.run(['git', 'apply', '-'], cwd=source, input=patch, text=True, check=True)
    if boot_patch:
        subprocess.run(['git', 'apply', '--check', '-'], cwd=source, input=boot_patch, text=True, check=True)
        subprocess.run(['git', 'apply', '-'], cwd=source, input=boot_patch, text=True, check=True)
    (output / 'candidate-boot-hash.patch').write_text(boot_patch)
    if args.boot_bundle_receipt:
        shutil.copy2(args.boot_bundle_receipt, output / 'input-boot-bundle-receipt.json')
    boot = source / 'mkosi.images/sysupdate/mkosi.profiles/m4-mini/mkosi.extra/efi/m1n1/boot.bin'
    boot.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.boot_bundle, boot)
    if digest(boot) != expected_boot:
        raise ValueError('copied boot bundle mismatch')
    (source / 'mkosi.version').write_text(args.image_version + '\n')
    env = dict(os.environ, PYTHONPATH=str(args.mkosi_source.resolve()))
    options = ['--profile=daily', '--profile=m4-mini', '--architecture=arm64',
               '--image-version=' + args.image_version, '--package-directory=' + str(packages),
               '--output-directory=' + str(output / 'images'),
               '--workspace-directory=' + str(output / 'workspace'),
               '--cache-directory=' + str(output / 'cache'),
               '--package-cache-directory=' + str(output / 'package-cache')]
    summary = subprocess.check_output([sys.executable, '-m', 'mkosi', *options, '--json', 'summary'], cwd=source, env=env, text=True)
    (output / 'summary.json').write_text(summary)
    graph = {image['Image'] for image in json.loads(summary)['Images']}
    if not {'base', 'apple-silicon', 'liveiso', 'sysupdate'} <= graph:
        raise ValueError('complete M4 desktop/boot graph must be retained')
    commands = []
    if not args.summary_only:
        prefix = ([] if args.hosted_root else ['unshare', '--user', '--map-auto', '--map-root-user', '--mount', '--pid', '--fork']) + [sys.executable, '-m', 'mkosi']
        for verb in ['genkey', 'build']:
            command = prefix + options + [verb]
            commands.append(command)
            with (output / (verb + '.log')).open('wb') as log:
                subprocess.run(command, cwd=source, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    (output / 'receipt.json').write_text(json.dumps({
        'scope': 'full M4 mkosi graph summary' if args.summary_only else 'full M4 mkosi graph build; ISO assembly separate',
        'source_commit': revision, 'driver_sha256': digest(Path(__file__)),
        'image_version': args.image_version, 'images': sorted(graph), 'commands': commands,
        'candidate_package_hashes': {name: item['sha256'] for name, item in candidate['components'].items()},
        'boot_bundle_sha256': expected_boot, 'candidate_boot_hash_patch_applied_in_clone': bool(boot_patch), 'candidate_hash_patch_applied_in_clone': bool(patch),
        'summary_only': args.summary_only, 'execution_identity': 'hosted root' if args.hosted_root else 'mapped namespace', 'mkosi_build_passed': not args.summary_only,
        'iso_assembled': False, 'factory_promotion': False, 'installer_admission': False,
        'hardware_validated': False}, indent=2) + '\n')
    marker.unlink()
    print('Full graph resolved' if args.summary_only else 'Full mkosi graph built; ISO assembly and native qualification still required')


if __name__ == '__main__':
    main()
