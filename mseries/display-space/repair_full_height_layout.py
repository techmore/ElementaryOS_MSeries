#!/usr/bin/env python3
"""Migrate saved J314 cropped-panel layouts after a verified full-height boot.

Writes only explicit input files. Inspect and back them up first. This does not
apply a monitor mode, alter dock/external settings or discover machine identity.
"""
import argparse
import glob
import json
from pathlib import Path
import xml.etree.ElementTree as ET


def repair_profiles(data):
    for profile in data['profiles'].values():
        for logical in profile['layout']:
            for monitor in logical['monitors']:
                if monitor['key'] == 'builtin' and monitor['mode'].startswith('3024x1890@'):
                    monitor['mode'] = monitor['mode'].replace('3024x1890@', '3024x1964@', 1)
    return data


def repair_monitors(root):
    for logical in root.findall('.//logicalmonitor'):
        for monitor in logical.findall('monitor'):
            if (monitor.findtext('monitorspec/connector', '').startswith('eDP') and
                    monitor.findtext('mode/width') == '3024' and
                    monitor.findtext('mode/height') == '1890'):
                monitor.find('mode/height').text = '1964'
                # 1.5 is not supported by the full-height mode; use its 2x scale.
                logical.find('scale').text = '2'
    return root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profiles', type=Path)
    parser.add_argument('--monitors', type=Path)
    guard = parser.add_mutually_exclusive_group(required=True)
    guard.add_argument('--full-height-verified', action='store_true',
                       help='confirm the J314 eDP advertises 3024x1964 and 2x scale')
    guard.add_argument('--check-running-panel', action='store_true',
                       help='skip unless this is the full-height J314 M1 Pro panel')
    args = parser.parse_args()
    if args.check_running_panel:
        try:
            model = Path('/proc/device-tree/model').read_text()
            enabled = Path('/sys/module/appledrm/parameters/show_notch').read_text().strip()
            modes = [Path(p).read_text().splitlines() for p in glob.glob('/sys/class/drm/card*-eDP-*/modes')]
        except OSError:
            return
        if '14-inch, M1 Pro' not in model or enabled != 'Y' or not any('3024x1964' in m for m in modes):
            return
    if not args.profiles and not args.monitors:
        parser.error('specify a saved layout file')
    if args.profiles and args.profiles.exists():
        data = repair_profiles(json.loads(args.profiles.read_text()))
        args.profiles.write_text(json.dumps(data, indent=2, sort_keys=True) + '\n')
    if args.monitors and args.monitors.exists():
        root = repair_monitors(ET.fromstring(args.monitors.read_text()))
        ET.indent(root)
        args.monitors.write_text(ET.tostring(root, encoding='unicode') + '\n')


if __name__ == '__main__':
    main()
