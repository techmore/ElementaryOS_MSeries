#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Package validated private-prefix Gravity Mesa; never activate or install it."""
import argparse
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('mesa_compatibility', HERE / 'mesa-compatibility.py')
compatibility = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compatibility)

NAME = 'elementary-m4-gravity-mesa1'
VERSION = compatibility.CURRENT_VERSION
COMMIT = '87ac51d411f0e58a9433567ec2666f457be89e1d'
ARCHIVE_SHA = '1195f212bcf5816b8b893113b0b5dc578ce744d420856b6ad4f42008889e231e'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--stage', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--validation', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compatibility-version', default=VERSION)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new output directory required')
    validation = json.loads(args.validation.read_text())
    version = args.compatibility_version
    selected = compatibility.metadata(version, validation)
    compatibility.source_gate(args.source, version)
    if (validation['commit'] != COMMIT or validation['build'] != 'passed' or
            validation['tests']['failed_groups'] != 0 or validation['tests']['meson_groups'] != 5):
        raise ValueError('matching successful Mesa validation required')
    required = {'lib/libvulkan_asahi.so', 'lib/libgallium-26.3.0-devel.so',
                'lib/libEGL_mesa.so.0.0.0', 'lib/libGLX_mesa.so.0.0.0'}
    if set(validation.get('artifacts', {})) != required:
        raise ValueError('all four validated graphics libraries are required')
    if digest(args.archive) != ARCHIVE_SHA:
        raise ValueError('corresponding source archive checksum mismatch')
    prefix = args.stage / 'opt/elementary-m4-gravity1'
    for path, expected in validation['artifacts'].items():
        if Path(path).is_absolute() or '..' in Path(path).parts:
            raise ValueError('unsafe validation path')
        if digest(prefix / path) != expected:
            raise ValueError('staged library hash mismatch: ' + path)
    args.output.mkdir(parents=True)
    bundle = compatibility.source_bundle(args.output / compatibility.BUNDLE_NAME, args.source, version) if selected['patches'] else None
    with tempfile.TemporaryDirectory(prefix='m4-mesa-package-') as temp:
        root = Path(temp)
        payload = root / 'debian' / NAME
        # Keep all bytes in /usr: factory sysupdate retains only that tree.
        # Mesa's compiled /opt paths remain valid through a compatibility link.
        persistent = payload / 'usr/lib/elementary-m4-gravity1'
        shutil.copytree(prefix, persistent, symlinks=True)
        (payload / 'opt').mkdir()
        (payload / 'opt/elementary-m4-gravity1').symlink_to('/usr/lib/elementary-m4-gravity1')
        tmpfiles = payload / 'usr/lib/tmpfiles.d/elementary-m4-mesa.conf'
        tmpfiles.parent.mkdir(parents=True, exist_ok=True)
        tmpfiles.write_text('# Restore compatibility after /usr-only factory image installation.\n'
                            'L /opt/elementary-m4-gravity1 - - - - /usr/lib/elementary-m4-gravity1\n')
        launcher = persistent / 'bin/run-mesa'
        launcher.parent.mkdir(exist_ok=True)
        shutil.copy2(Path(__file__).with_name('run-mesa.py'), launcher)
        launcher.chmod(0o755)
        docs = payload / 'usr/share/doc' / NAME
        docs.mkdir(parents=True)
        shutil.copytree(args.source / 'licenses', docs / 'licenses')
        shutil.copy2(args.source / 'docs/license.rst', docs / 'license.rst')
        shutil.copy2(args.validation, docs / 'validation.json')
        if bundle:
            shutil.copy2(args.output / bundle['file'], docs / bundle['file'])
            supplemental = docs / 'supplemental-tests'
            supplemental.mkdir()
            if set(validation['supplemental_test_receipts']) != compatibility.supplemental_receipt_names(version):
                raise ValueError('versioned supplemental test receipts required')
            for name, expected in validation['supplemental_test_receipts'].items():
                receipt = args.validation.parent / (name + '-tests') / 'receipt.json'
                if digest(receipt) != expected:
                    raise ValueError('supplemental test receipt changed')
                shutil.copy2(receipt, supplemental / (name + '.json'))
        (docs / 'README').write_text('Experimental private-prefix Mesa. No global activation or boot hooks.\nRequires matched M4 kernel/firmware. Software tests are not M4 GPU qualification.\n')
        debian = root / 'debian'
        debian.mkdir(exist_ok=True)
        control = (f'Package: {NAME}\nVersion: {version}\nArchitecture: arm64\n'
                   'Maintainer: ElementaryOS MSeries contributors <builder@localhost>\n'
                   'Section: graphics\nPriority: optional\n'
                   'Description: Experimental M4 private-prefix graphics libraries\n'
                   ' No system graphics replacement or automatic activation.\n')
        (debian / 'control').write_text('Source: ' + NAME + '\n\n' + control)
        packaged_prefix = persistent
        libraries = [p for p in (packaged_prefix / 'lib').glob('*.so*') if p.is_file() and not p.is_symlink()]
        result = subprocess.run(['dpkg-shlibdeps', '--ignore-missing-info', '-O',
                                 '-l' + str((packaged_prefix / 'lib').resolve())] +
                                ['-e' + str(p.resolve()) for p in libraries],
                                cwd=root, capture_output=True, text=True, check=True)
        (args.output / 'dependencies.log').write_text(result.stdout + result.stderr)
        dependencies = 'python3, libegl1, libgl1, libvulkan1, ' + next(line.split('=', 1)[1] for line in result.stdout.splitlines()
                            if line.startswith('shlibs:Depends='))
        (payload / 'DEBIAN').mkdir()
        (payload / 'DEBIAN/control').write_text(control + 'Depends: ' + dependencies + '\n')
        package = args.output / f'{NAME}_{version}_arm64.deb'
        subprocess.run(['dpkg-deb', '-Zzstd', '-z3', '--threads-max=2', '--root-owner-group',
                        '--build', str(payload), str(package)], check=True)
    shutil.copy2(args.archive, args.output / 'gravity-mesa-corresponding-source.tar.gz')
    (args.output / 'receipt.json').write_text(json.dumps({
        'commit': COMMIT, 'package': package.name, 'package_sha256': digest(package),
        'package_version': version, 'compatibility_patches': selected['patches'],
        'patched_sources_sha256': selected['patched_sources_sha256'], 'supplemental_tests': selected['supplemental_tests'],
        'compatibility_source_archive': bundle,
        'source_archive_sha256': ARCHIVE_SHA, 'dependencies': dependencies,
        'status': 'private-prefix payload packaged; no installation, activation or M4 GPU qualification',
    }, indent=2) + '\n')


if __name__ == '__main__':
    main()
