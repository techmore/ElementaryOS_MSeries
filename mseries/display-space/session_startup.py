#!/usr/bin/env python3
"""Stop Gala waiting for a panel when the owner's dock is deliberately disabled.

Only adjusts the panel wait count. The disabled marker, guarded dock command,
other shell clients and session types are preserved. Takes effect next login.
"""
import argparse
import configparser
from pathlib import Path


def prepare(text, disabled):
    config = configparser.ConfigParser(interpolation=None)
    config.optionxform = str
    config.read_string(text)
    if not disabled or not config.has_section('io.elementary.dock'):
        return text
    config.set('io.elementary.dock', 'wait-for-n-panels', '0')
    import io
    output = io.StringIO()
    config.write(output, space_around_delimiters=False)
    return output.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--disabled-marker', type=Path, required=True)
    args = parser.parse_args()
    text = args.source.read_text()
    result = prepare(text, args.disabled_marker.exists())
    if result == text:
        print('No disabled-dock wait to repair')
        return
    if args.output.exists() and args.output != args.source:
        parser.error('output already exists; use it as --source to preserve overrides')
    if args.output.exists() and args.output.read_text() == result:
        print('Disabled-dock wait already repaired')
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(result)
    print('Set disabled-dock panel wait to zero; effective next login')


if __name__ == '__main__':
    main()
