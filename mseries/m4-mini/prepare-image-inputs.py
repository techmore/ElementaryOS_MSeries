#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Validate research components and prepare isolated image inputs, never install.

Writes a candidate-only live-kernel hash patch; does not apply it or alter the
checked-in factory references. Input receipts must come from trusted builds.
"""
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HOOK = 'mkosi.images/liveiso/mkosi.profiles/m4-mini/prepare-live-kernel.chroot'
SOURCE_ARCHIVES = {
    'kernel': ('gravity-linux-corresponding-source.tar.gz', '045c64540fa4210394c899cad6320c5bf9090a66919938d986aeaad0033946e8'),
    'mesa': ('gravity-mesa-corresponding-source.tar.gz', '1195f212bcf5816b8b893113b0b5dc578ce744d420856b6ad4f42008889e231e'),
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()



def live_hook_patch(original, baseline, build):
    changed = original
    for old, new in [(baseline['artifacts']['arch/arm64/boot/Image'], build['artifacts']['arch/arm64/boot/Image']),
                     (baseline['config_sha256'], build['config_sha256'])]:
        if changed.count(old) != 1:
            raise ValueError('live hook no longer matches reviewed baseline')
        changed = changed.replace(old, new)
    return ''.join(difflib.unified_diff(original.splitlines(True), changed.splitlines(True),
                                       fromfile='a/' + HOOK, tofile='b/' + HOOK))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--kernel-package-receipt', type=Path, required=True)
    parser.add_argument('--kernel-build-receipt', type=Path, required=True)
    parser.add_argument('--mesa', type=Path, required=True)
    parser.add_argument('--mesa-package-receipt', type=Path, required=True)
    parser.add_argument('--mesa-build-receipt', type=Path, required=True)
    parser.add_argument('--smoke', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new candidate workspace required')
    for name in SOURCE_ARCHIVES:
        package = getattr(args, name)
        expected_name, expected_sha = SOURCE_ARCHIVES[name]
        archive = package.resolve().parent / expected_name
        if digest(archive) != expected_sha:
            raise ValueError('corresponding source mismatch: ' + name)
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    records = args.output / 'records'
    records.mkdir()
    for name in ['kernel', 'mesa']:
        command = [sys.executable, str(HERE / ('check-' + name + '-package.py')),
                   '--package', str(getattr(args, name).resolve()), '--package-receipt',
                   str(getattr(args, name + '_package_receipt').resolve()), '--build-receipt',
                   str(getattr(args, name + '_build_receipt').resolve()),
                   '--receipt', str((records / (name + '-check.json')).resolve())]
        if name == 'mesa':
            command += ['--smoke', str(args.smoke.resolve())]
        subprocess.run(command, check=True)
    subprocess.run([sys.executable, str(HERE / 'package-policy.py'),
                    '--output', str((args.output / 'policy-build').resolve())], check=True)
    policy = json.loads((args.output / 'policy-build/receipt.json').read_text())
    packages = args.output / 'packages'
    packages.mkdir()
    components = {}
    for name in ['kernel', 'mesa']:
        package = getattr(args, name).resolve()
        package_receipt = getattr(args, name + '_package_receipt')
        build_receipt = getattr(args, name + '_build_receipt')
        recorded = json.loads(package_receipt.read_text())
        if recorded['package'] != package.name or not package.name.endswith('.deb'):
            raise ValueError('package filename/receipt mismatch')
        shutil.copy2(package, packages / package.name)
        if digest(packages / package.name) != recorded['package_sha256']:
            raise ValueError('copied package checksum mismatch: ' + name)
        shutil.copy2(package_receipt, records / (name + '-package.json'))
        shutil.copy2(build_receipt, records / (name + '-build.json'))
        archive_name, archive_sha = SOURCE_ARCHIVES[name]
        # Keep required corresponding source with this isolated build workspace.
        shutil.copy2(package.parent / archive_name, args.output / archive_name)
        if digest(args.output / archive_name) != archive_sha:
            raise ValueError('copied source checksum mismatch: ' + name)
        components[name] = {'file': package.name, 'sha256': digest(packages / package.name),
                            'source_archive_sha256': archive_sha}
        extra = recorded.get('compatibility_source_archive')
        if extra is not None:
            if name != 'mesa' or extra['file'] != 'gravity-mesa-compatibility-source.tar.gz':
                raise ValueError('unexpected additional corresponding source')
            archive = package.parent / extra['file']
            if digest(archive) != extra['sha256']:
                raise ValueError('additional corresponding source changed')
            shutil.copy2(archive, args.output / extra['file'])
            components[name]['additional_source_archives'] = {extra['file']: extra['sha256']}
    policy_package = args.output / 'policy-build' / policy['package']
    shutil.copy2(policy_package, packages / policy_package.name)
    if digest(packages / policy_package.name) != policy['package_sha256']:
        raise ValueError('copied policy checksum mismatch')
    components['policy'] = {'file': policy_package.name, 'sha256': digest(packages / policy_package.name)}
    shutil.copy2(args.output / 'policy-build/receipt.json', records / 'policy-package.json')
    build = json.loads(args.kernel_build_receipt.read_text())
    baseline = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
    original = (REPO / HOOK).read_text()
    patch = live_hook_patch(original, baseline, build)
    patch_path = args.output / 'candidate-live-kernel.patch'
    patch_path.write_text(patch)
    if patch:
        subprocess.run(['git', 'apply', '--check', str(patch_path.resolve())], cwd=REPO, check=True)
    (args.output / 'candidate.json').write_text(json.dumps({
        'schema': 1, 'scope': 'validated research image inputs; source checkout and factory pins untouched',
        'preparer_sha256': digest(Path(__file__)),
        'recipe_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'components': components, 'live_hook_patch_required': bool(patch),
        'live_hook_patch_sha256': digest(patch_path),
        'kernel_image_sha256': build['artifacts']['arch/arm64/boot/Image'],
        'kernel_config_sha256': build['config_sha256'],
        'factory_promotion': False, 'installer_admission': False, 'hardware_validated': False,
    }, indent=2) + '\n')
    (args.output / 'README').write_text(
        'Unpromoted research inputs only. Package/source/validation records are retained here.\n'
        'For an explicitly selected disposable image build, apply a nonempty candidate-live-kernel.patch\n'
        'with git apply --check then git apply, and pass packages/ via --package-directory.\n'
        'The patch only updates hash checks to the validated candidate; it does not remove checks.\n'
        'This tool did not apply the patch or change repository/factory references.\n'
        'No image, boot, installation or physical M4 qualification is implied.\n')
    marker.unlink()
    print('Research image inputs validated and staged; factory pins and source checkout unchanged')


if __name__ == '__main__':
    main()
