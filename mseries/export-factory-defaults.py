#!/usr/bin/env python3
"""Export overlay-owned /etc files into /usr for an immutable image.

Generated tmpfiles entries create missing defaults without replacing local edits.
Run after overlay pruning: exporting an entire build root's /etc would claim
ownership of unrelated distribution configuration.
"""
from pathlib import Path
import argparse
import shutil


def escape(value):
    # tmpfiles splits whitespace and expands specifiers, even in path fields.
    return str(value).replace('\\', r'\x5c').replace('%', '%%').replace(' ', r'\x20').replace('\t', r'\x09').replace('\n', r'\x0a').replace('\r', r'\x0d')


def export(root, owned=None):
    root = Path(root)
    etc = root / 'etc'
    factory = root / 'usr/share/factory/etc'
    lines = ['# M-series overlay defaults. Preserve existing administrator settings.']
    if etc.exists():
        for source in sorted(etc.rglob('*')):
            relative = source.relative_to(etc)
            if owned is not None and relative.as_posix() not in owned:
                continue
            target = factory / relative
            live = '/etc/' + relative.as_posix()
            if source.is_symlink():
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.is_symlink() or target.exists():
                    target.unlink()
                target.symlink_to(source.readlink())
                lines.append(f'L {escape(live)} - - - - {escape(source.readlink())}')
            elif source.is_dir():
                continue
            elif source.is_file():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                lines.append(f'C {escape(live)} - - - - {escape("/usr/share/factory/etc/" + relative.as_posix())}')
            else:
                raise ValueError(f'Unsupported configuration entry: {source}')
    output = root / 'usr/lib/tmpfiles.d/mseries-overlay-defaults.conf'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--source-extra', type=Path, action='append')
    parser.add_argument('--include', action='append', default=[])
    args = parser.parse_args()
    owned = None
    if args.source_extra:
        owned = set(args.include)
        for extra in args.source_extra:
            extra_etc = extra / 'etc'
            owned |= {p.relative_to(extra_etc).as_posix() for p in extra_etc.rglob('*')
                      if p.is_file() or p.is_symlink()}
    export(args.root, owned)
