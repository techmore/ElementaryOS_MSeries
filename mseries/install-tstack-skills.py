#!/usr/bin/env python3
"""Install the pinned, vendored tstack workflows for local Codex and Claude Code.

Existing identical files are reused. Modified skills are never overwritten.
"""
import argparse
from pathlib import Path
import shutil

NAMES = ('full-send', 'full-stop', 'council', 'sol-loop', 'file-pr', 'takeover',
         'babysit-pr', 'modernize', 'leaving-pr-comments')
REVISION = '7de017b3fc9d50c03cf3ecb98fb71e0ca65a78bd'


def install(home: Path, source: Path, check=False):
    files = []
    for agent in ('.codex', '.claude'):
        for name in NAMES:
            for origin in sorted((source / name).rglob('*')):
                if origin.is_file():
                    files.append((origin, home / agent / 'skills' / name / origin.relative_to(source / name)))
        files.append((source / 'TSTACK-LICENSE.txt', home / agent / 'skills' / 'TSTACK-LICENSE.txt'))
    # Preflight all destinations before copying anything; retain user edits.
    for origin, target in files:
        if target.is_symlink() or (target.exists() and (not target.is_file() or target.read_bytes() != origin.read_bytes())):
            raise SystemExit(f'Preserved differing file: {target}')
        if check and not target.is_file():
            raise SystemExit(f'Missing skill file: {target}')
    if not check:
        for origin, target in files:
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(origin, target)
            # The GitHub archive installer loses executable modes; preserve the
            # upstream helper's 100755 mode without altering any skill text.
            if origin.name == 'pr-wait':
                target.chmod(0o755)
    print(f'{"Verified" if check else "Installed"} all nine tstack skills for Codex and Claude Code at {REVISION}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home', type=Path, default=Path.home())
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    prefix = Path(__file__).resolve().parents[1]
    source = prefix / '.agents' / 'skills'
    if not source.is_dir():
        source = prefix / 'share' / 'mseries' / 'tstack'
    install(args.home, source, args.check)
