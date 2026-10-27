#!/usr/bin/env python3
"""Fail when a change touches a path whose source of truth moved to mseries-sdk-apps.

Usage: check_frozen.py [--allow] BASE HEAD
Paths come from mseries/ci/frozen-paths.txt. FROZEN.md files are exempt.
--allow (the `allow-frozen-edit` label) reports the hits but exits 0.
"""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / 'mseries/ci/frozen-paths.txt'


def frozen_paths():
    lines = (line.strip() for line in MANIFEST.read_text().splitlines())
    return [line.rstrip('/') for line in lines if line and not line.startswith('#')]


def is_frozen(path, frozen):
    if path.rsplit('/', 1)[-1] == 'FROZEN.md':
        return False
    return any(path == f or path.startswith(f + '/') for f in frozen)


def hits(changed, frozen):
    return sorted(p for p in changed if is_frozen(p, frozen))


def changed_files(base, head):
    # --no-renames lists both sides of a rename, so a move out of a frozen dir is caught.
    out = subprocess.run(
        ['git', 'diff', '--name-only', '--no-renames', f'{base}...{head}'],
        cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def main(argv):
    allow = '--allow' in argv
    args = [a for a in argv if a != '--allow']
    if len(args) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    found = hits(changed_files(*args), frozen_paths())
    if not found:
        print('No frozen paths modified.')
        return 0
    print('Frozen paths modified (source of truth: techmore/mseries-sdk-apps):')
    for path in found:
        print(f'  {path}')
    if allow:
        print('Label allow-frozen-edit is set; allowing.')
        return 0
    print('::error::Edit these in techmore/mseries-sdk-apps, or add the '
          '`allow-frozen-edit` label to this PR. See mseries/REPO-OWNERSHIP.md.')
    return 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
