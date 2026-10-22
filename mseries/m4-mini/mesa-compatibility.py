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
