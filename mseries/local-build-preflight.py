#!/usr/bin/env python3
"""Read-only capacity/tool check for a local OS 9 image build."""
import argparse
import json
from pathlib import Path
import platform
import shutil

MIN_FREE = 60 * 1024**3  # Conservative headroom, not a measured peak requirement.
TOOLS = ('just', 'podman', 'zstd', 'rsync', 'cargo')


def existing_parent(path):
    path = Path(path).expanduser().resolve()
    while not path.exists():
        path = path.parent
    return path


def report(directory):
    filesystem = existing_parent(directory)
    available = shutil.disk_usage(filesystem).free
    missing = [tool for tool in TOOLS if shutil.which(tool) is None]
    arch = platform.machine()
    blockers = []
    if arch not in ('aarch64', 'arm64'):
        blockers.append('This M-series preflight requires a native ARM64 host.')
    if missing:
        blockers.append('Missing tools: ' + ', '.join(missing))
    if available < MIN_FREE:
        blockers.append('Insufficient disk headroom for the full image build.')
    return {'directory': str(Path(directory).expanduser().resolve()),
            'filesystem_checked': str(filesystem), 'architecture': arch,
            'free_gib': round(available / 1024**3, 1),
            'minimum_free_gib': MIN_FREE // 1024**3,
            'additional_gib_needed': round(max(0, MIN_FREE - available) / 1024**3, 1),
            'missing_tools': missing, 'ready': not blockers, 'blockers': blockers,
            'policy': 'Conservative disk guard; no measured peak claim. No files changed.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    result = report(args.directory)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['ready'] else 2)
