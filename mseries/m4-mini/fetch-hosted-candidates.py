#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Retrieve successful, explicitly selected research artifacts; never install them.

GitHub metadata establishes repository/workflow provenance, not an independent
signature or hardware qualification. Run IDs and expected source SHAs are required.
Package semantics are checked separately by prepare-image-inputs.py.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import zipfile

REPOSITORY = 'techmore/ElementaryOS_MSeries'
WORKFLOW = '.github/workflows/daily-9.0.yml'
KINDS = {'kernel': 'build-m4-kernel', 'mesa': 'build-m4-userspace'}


def api(path):
    return json.loads(subprocess.check_output(['gh', 'api', path], text=True))


def pages(path, key):
    result = []
    page = 1
    while True:
        batch = api(f'{path}?per_page=100&page={page}')[key]
        result.extend(batch)
        if len(batch) < 100:
            return result
        page += 1


def validate_run(run, jobs, kind, expected_sha, run_id):
    if not re.fullmatch(r'[0-9a-f]{40}', expected_sha):
        raise ValueError('full expected source SHA required')
    if (run['id'] != run_id or run['repository']['full_name'] != REPOSITORY
            or run['head_repository']['full_name'] != REPOSITORY
            or run['path'] != WORKFLOW or run['event'] != 'workflow_dispatch'
            or run['head_sha'] != expected_sha or run['status'] != 'completed'
            or run['conclusion'] != 'success'):
        raise ValueError('run is not a successful matched repository/workflow/source build')
    selected = [job for job in jobs if job['name'] == KINDS[kind]]
    if len(selected) != 1 or selected[0]['conclusion'] != 'success' or selected[0]['status'] != 'completed':
        raise ValueError('required component job did not succeed')


def select_artifact(artifacts, kind, run_id):
    matches = [item for item in artifacts if item['name'] == f'm4-{kind}-candidate-{run_id}']
    if len(matches) != 1 or matches[0]['expired']:
        raise ValueError('one unexpired candidate artifact required')
    return matches[0]


def extract(archive, target):
    with zipfile.ZipFile(archive) as source:
        members = source.infolist()
        if sum(item.file_size for item in members) > 3 * 1024**3:
            raise ValueError('candidate archive exceeds extraction limit')
        seen = set()
        for item in members:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            if (path.is_absolute() or '..' in path.parts or '\\' in item.filename
                    or not path.parts or path in seen or stat.S_ISLNK(mode)):
                raise ValueError('unsafe or duplicate artifact member')
            seen.add(path)
        source.extractall(target)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_payload(target, expected_sha):
    if (target / 'source-commit.txt').read_text().strip() != expected_sha:
        raise ValueError('artifact source commit differs from run')
    actual = {p.name for p in target.iterdir() if p.name.endswith(('.deb', '.tar.gz'))}
    recorded = {}
    for line in (target / 'SHA256SUMS').read_text().splitlines():
        match = re.fullmatch(r'([0-9a-f]{64})  ([A-Za-z0-9_.+~%-]+)', line)
        if not match or match[2] in recorded:
            raise ValueError('invalid or duplicate package/source checksum entry')
        recorded[match[2]] = match[1]
    if not actual or set(recorded) != actual:
        raise ValueError('checksum manifest must cover exactly packages and corresponding source')
    for name, expected in recorded.items():
        if digest(target / name) != expected:
            raise ValueError('artifact checksum mismatch: ' + name)
    if len([name for name in actual if name.endswith('.deb')]) != 1:
        raise ValueError('one component package required')
    return recorded


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for kind in KINDS:
        parser.add_argument('--' + kind + '-run', type=int, required=True)
        parser.add_argument('--' + kind + '-source', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new retrieval directory required')
    # Check both remote runs before writing or downloading any payload.
    candidates = {}
    for kind in KINDS:
        run_id = getattr(args, kind + '_run')
        expected = getattr(args, kind + '_source')
        endpoint = f'repos/{REPOSITORY}/actions/runs/{run_id}'
        run = api(endpoint)
        validate_run(run, pages(endpoint + '/jobs', 'jobs'), kind, expected, run_id)
        candidates[kind] = (run, select_artifact(pages(endpoint + '/artifacts', 'artifacts'), kind, run_id))
    args.output.mkdir(parents=True)
    marker = args.output / 'INCOMPLETE'
    marker.touch()
    records = {}
    for kind, (run, artifact) in candidates.items():
        archive = args.output / (kind + '.zip')
        with archive.open('xb') as stream:
            subprocess.run(['gh', 'api', f"repos/{REPOSITORY}/actions/artifacts/{artifact['id']}/zip"], stdout=stream, check=True)
        target = args.output / kind
        target.mkdir()
        extract(archive, target)
        hashes = verify_payload(target, run['head_sha'])
        # ZIP extraction does not retain executable bits. This binary will only
        # run later in the explicitly invoked Mesa package validation step.
        if kind == 'mesa':
            (target / 'mesa-software').chmod(0o755)
        records[kind] = {'run_id': run['id'], 'source_commit': run['head_sha'],
                         'run_url': run['html_url'], 'artifact_id': artifact['id'],
                         'github_artifact_digest': artifact.get('digest'),
                         'download_sha256': digest(archive), 'payload_sha256': hashes}
        archive.unlink()
    (args.output / 'provenance.json').write_text(json.dumps({
        'scope': 'GitHub repository/workflow provenance and payload checksums; package validation still required',
        'repository': REPOSITORY, 'components': records, 'hardware_validated': False,
        'factory_promotion': False, 'installer_admission': False}, indent=2) + '\n')
    marker.unlink()
    print('Candidate retrieval verified. Run prepare-image-inputs.py before image use.')


if __name__ == '__main__':
    main()
