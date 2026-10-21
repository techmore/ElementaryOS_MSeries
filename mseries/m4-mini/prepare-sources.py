#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Fetch immutable public research sources; never install or enable a kernel."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import urllib.request

HERE = Path(__file__).resolve().parent


def prepare(profile, output):
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
    output.mkdir(parents=True)
    receipt = {'profile': profile, 'status': 'research-only; no J773g hardware qualification', 'files': []}
    try:
        for source in profile['sources']:
            for path in source['files']:
                url = f"https://raw.githubusercontent.com/{source['repository']}/{source['commit']}/{path}"
                with urllib.request.urlopen(url, timeout=60) as response:
                    content = response.read()
                target = output / source['name'] / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                receipt['files'].append({'path': str(target.relative_to(output)), 'url': url,
                                         'sha256': hashlib.sha256(content).hexdigest()})
    except Exception:
        (output / 'INCOMPLETE').write_text('Fetch failed; this is not a complete source receipt.\n')
        raise
    (output / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(json.loads((HERE / 'research.json').read_text()), args.output)
    print(f"Captured {len(result['files'])} source files; no build or boot qualification claimed")
