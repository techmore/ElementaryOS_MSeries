#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Exact source/version gates for reviewed M4 Mesa research compatibility."""
import hashlib
import json
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
DIRECTORY = HERE / 'gravity/mesa-compatibility'
MANIFEST = json.loads((DIRECTORY / 'manifest.json').read_text())
CURRENT_VERSION = MANIFEST['current_research_version']
HISTORICAL_VERSION = '26.3.0~devel+gravity.87ac51d-4'


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def snapshot(version):
    if version not in MANIFEST['versions']:
        raise ValueError('unsupported Mesa compatibility version')
    return MANIFEST['versions'][version]


def check_files(source, expected):
    for name, value in expected.items():
        p = Path(name)
        if p.is_absolute() or '..' in p.parts or digest(source / p) != value:
            raise ValueError('Mesa source hash mismatch: ' + name)


def source_gate(source, version=CURRENT_VERSION):
    selected = snapshot(version)
    expected = selected['patched_sources_sha256'] or MANIFEST['baseline_sources_sha256']
    check_files(source, expected)
    return dict(selected['patched_sources_sha256'])


def metadata(version, build, package=None):
    selected = snapshot(version)
    if build.get('package_version', HISTORICAL_VERSION) != version:
        raise ValueError('Mesa build/package version mismatch')
    if package is not None and package.get('package_version', HISTORICAL_VERSION) != version:
        raise ValueError('Mesa package receipt version mismatch')
    for field, expected in [('compatibility_patches', selected['patches']),
                            ('patched_sources_sha256', selected['patched_sources_sha256']),
                            ('supplemental_tests', selected['supplemental_tests'])]:
        if build.get(field, {}) != expected:
            raise ValueError('Mesa build compatibility differs from frozen version: ' + field)
        if package is not None and package.get(field, {}) != expected:
            raise ValueError('Mesa package compatibility differs from frozen version: ' + field)
    return selected


def apply(source, log, version=CURRENT_VERSION):
    selected = snapshot(version)
    check_files(source, MANIFEST['baseline_sources_sha256'])
    if version == HISTORICAL_VERSION:
        return source_gate(source, version)
    for phase in MANIFEST['phases']:
        patch = DIRECTORY / phase['file']
        if digest(patch) != phase['sha256'] or selected['patches'].get(phase['file']) != phase['sha256']:
            raise ValueError('Mesa compatibility patch checksum mismatch')
        check_files(source, phase['before'])
        result = subprocess.run(['patch', '--batch', '--fuzz=0', '--no-backup-if-mismatch',
                                 '-p1', '-i', str(patch.resolve())], cwd=source, capture_output=True)
        with log.open('ab') as stream:
            stream.write(result.stdout + result.stderr)
        if result.returncode:
            raise ValueError('Mesa compatibility patch did not apply: ' + phase['file'])
        check_files(source, phase['after'])
    return source_gate(source, version)


BUNDLE_NAME = 'gravity-mesa-compatibility-source.tar.gz'
BUNDLE_ROOT = 'm4-mesa-reproduction'


def source_bundle(output, source):
    """Ship the base-archive patches and build/test recipes without binary data."""
    import gzip
    import io
    import tarfile
    files = {}
    for name in ['build-mesa.py', 'package-mesa.py', 'check-mesa-package.py',
                 'run-mesa.py', 'mesa-compatibility.py', 'test-mesa-software.c',
                 'testing/mesa/test-helper-divergence.py', 'testing/mesa/test-rodata-upload.py']:
        files[name] = (HERE / name).read_bytes()
    for p in DIRECTORY.iterdir():
        if p.is_file():
            files['gravity/mesa-compatibility/' + p.name] = p.read_bytes()
    license_path = HERE.parents[1] / 'LICENSE'
    if not license_path.is_file():
        license_path = HERE / 'COPYING'
    files['COPYING'] = license_path.read_bytes()
    files['LICENSE-MIT'] = (source / 'licenses/MIT').read_bytes()
    files['SOURCE-SHA256SUMS'] = ''.join(
        hashlib.sha256(data).hexdigest() + '  ' + name + '\n'
        for name, data in sorted(files.items())).encode()
    with output.open('xb') as raw:
        with gzip.GzipFile(filename='', mode='wb', fileobj=raw, mtime=0) as zipped:
            with tarfile.open(fileobj=zipped, mode='w', format=tarfile.PAX_FORMAT) as archive:
                for name, data in sorted(files.items()):
                    info = tarfile.TarInfo(BUNDLE_ROOT + '/' + name)
                    info.size = len(data)
                    info.mode = 0o644
                    archive.addfile(info, io.BytesIO(data))
    verify_source_bundle(output, CURRENT_VERSION)
    return {'file': BUNDLE_NAME, 'sha256': digest(output)}


def verify_source_bundle(path, version):
    """Read only: validate source bundle boundaries, index and frozen patch set."""
    import tarfile
    selected = snapshot(version)
    with tarfile.open(path) as archive:
        data = {}
        total = 0
        for member in archive:
            p = Path(member.name)
            total += member.size
            if (not member.isfile() or len(p.parts) < 2 or p.parts[0] != BUNDLE_ROOT or
                    p.is_absolute() or '..' in p.parts or '\\' in member.name or
                    member.size < 0 or len(data) >= 100 or total > 20 * 1024**2):
                raise ValueError('unsafe compatibility source bundle')
            name = str(p.relative_to(BUNDLE_ROOT))
            if name in data:
                raise ValueError('duplicate source bundle member')
            data[name] = archive.extractfile(member).read()
    required = {'build-mesa.py', 'package-mesa.py', 'check-mesa-package.py', 'run-mesa.py',
                'mesa-compatibility.py', 'test-mesa-software.c', 'COPYING', 'LICENSE-MIT',
                'testing/mesa/test-helper-divergence.py', 'testing/mesa/test-rodata-upload.py',
                'gravity/mesa-compatibility/manifest.json',
                'gravity/mesa-compatibility/test-sources.json', 'SOURCE-SHA256SUMS'}
    if not required <= data.keys():
        raise ValueError('incomplete compatibility source bundle')
    index = {}
    for line in data['SOURCE-SHA256SUMS'].decode().splitlines():
        value, name = line.split('  ', 1)
        if name in index or len(value) != 64:
            raise ValueError('invalid source checksum index')
        index[name] = value
    actual = {name: hashlib.sha256(body).hexdigest() for name, body in data.items()
              if name != 'SOURCE-SHA256SUMS'}
    if actual != index:
        raise ValueError('source bundle checksum index mismatch')
    bundled = json.loads(data['gravity/mesa-compatibility/manifest.json'])
    if bundled['base_commit'] != MANIFEST['base_commit'] or bundled['versions'][version] != selected:
        raise ValueError('source bundle version differs from frozen contract')
    for name, expected in selected['patches'].items():
        if actual.get('gravity/mesa-compatibility/' + name) != expected:
            raise ValueError('source bundle patch mismatch: ' + name)
    return actual
