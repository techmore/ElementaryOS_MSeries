#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch immutable public research sources; never install or enable a kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request
import tarfile

HERE = Path(__file__).resolve().parent


def prepare(profile, output, archive_path=None):
    if output.exists():
        raise ValueError('output must be new; receipts are immutable')
    for source in profile['sources']:
        if not re.fullmatch(r'[0-9a-f]{40}', source['commit']):
            raise ValueError('sources require full immutable commit IDs')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', source['repository']):
            raise ValueError('invalid public repository')
        for path in source['files']:
            if Path(path).is_absolute() or '..' in Path(path).parts:
                raise ValueError('unsafe source path')
    archive = None
    if archive_path is not None:
        source = next(item for item in profile['sources'] if item['name'] == 'gravity-mini')
        pin = json.loads((HERE / 'receipts/2026-10-21-gravity-kernel-build.json').read_text())
        with archive_path.open('rb') as stream:
            archive_sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        if source['commit'] != pin['commit'] or archive_sha != pin['source_archive_sha256']:
            raise ValueError('matched pinned Gravity kernel archive required')
        archive = tarfile.open(archive_path)
    output.mkdir(parents=True)
    receipt = {'profile': profile, 'status': 'research-only; no J773g hardware qualification', 'files': []}
    try:
        for source in profile['sources']:
            if archive is not None and source['name'] != 'gravity-mini':
                continue
            for path in source['files']:
                url = f"https://raw.githubusercontent.com/{source['repository']}/{source['commit']}/{path}"
                if archive is None:
                    with urllib.request.urlopen(url, timeout=60) as response:
                        content = response.read()
                else:
                    member = 'linux-' + source['commit'] + '/' + path
                    with archive.extractfile(member) as response:
                        content = response.read()
                target = output / source['name'] / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                receipt['files'].append({'path': str(target.relative_to(output)), 'url': url,
                                         'sha256': hashlib.sha256(content).hexdigest()})
    except Exception:
        (output / 'INCOMPLETE').write_text('Fetch failed; this is not a complete source receipt.\n')
        raise
    finally:
        if archive is not None:
            archive.close()
    if archive_path is not None:
        receipt['archive_sha256'] = archive_sha
        receipt['capture_method'] = 'gravity-mini members from pinned complete kernel source archive'
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--gravity-archive', type=Path, help='capture only Gravity DT sources from the pinned kernel archive')
    args = parser.parse_args()
    result = prepare(json.loads((HERE / 'research.json').read_text()), args.output, args.gravity_archive)
    print(f"Captured {len(result['files'])} source files; no build or boot qualification claimed")
