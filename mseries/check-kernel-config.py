#!/usr/bin/env python3
"""Read-only Apple kernel capability gate; never installs or boots a kernel."""
import argparse
import hashlib
import json
from pathlib import Path

BASELINE = ('ARM64_16K_PAGES', 'DRM_APPLE', 'DRM_ASAHI', 'DRM_APPLE_AUDIO',
            'PHY_APPLE_ATC', 'SND_SOC_APPLE_MCA')
EXPERIMENTAL = ('RESET_APPLE_CIO', 'USB4_APPLE_SOC', 'VIDEO_APPLE_AVD')


def inspect(path, required):
    raw = path.read_bytes()
    values = {}
    for line in raw.decode().splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            name, value = line.split('=', 1)
            values[name[7:]] = value
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            values[line[9:-11]] = 'n'
    if not values:
        raise ValueError('No kernel configuration options found')
    symbols = {name: values.get(name, 'absent') for name in BASELINE + EXPERIMENTAL}
    missing = [name for name in required if values.get(name) not in ('y', 'm')]
    # The 16K page ABI is a boolean, unlike loadable hardware drivers.
    if 'ARM64_16K_PAGES' in required and values.get('ARM64_16K_PAGES') != 'y':
        if 'ARM64_16K_PAGES' not in missing:
            missing.append('ARM64_16K_PAGES')
    return dict(config=str(path), sha256=hashlib.sha256(raw).hexdigest(),
                symbols=symbols, missing_required=missing,
                scope='Configuration only; does not qualify firmware, modules or hardware boot')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', type=Path)
    parser.add_argument('--require', choices=('baseline', 'fairydust'), default='baseline',
                        help='fairydust additionally requires the experimental USB4/video symbols')
    args = parser.parse_args()
    required = BASELINE + (EXPERIMENTAL if args.require == 'fairydust' else ())
    try:
        report = inspect(args.config, required)
    except (OSError, UnicodeError, ValueError) as exc:
        parser.exit(2, f'{exc}\n')
    print(json.dumps(report, indent=2))
    return 1 if report['missing_required'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
