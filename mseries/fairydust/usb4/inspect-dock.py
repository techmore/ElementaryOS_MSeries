#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Read-only dock evidence collector. Connector state does not prove a dock picture."""
import argparse
import json
from pathlib import Path
import re
import struct
import subprocess

EXTERNAL = re.compile(r'card\d+-(?:DP-\d+(?:-\d+)*|HDMI-[A-Za-z]+-\d+)')
SOURCE = re.compile(r'DPINDBG connect_source: waited=(\d+) ret=(-?\d+).*?rate=(\d+) lanes=(\d+)')


def text(path):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return None


def cells(path):
    try:
        data = Path(path).read_bytes()
        return list(struct.unpack('>' + 'I' * (len(data) // 4), data)) if data and len(data) % 4 == 0 else None
    except OSError:
        return None


def command(argv):
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=30)
        return proc.stdout if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def routing(dt):
    """Resolve NHI's source phandle, rather than assuming dcpext1 or a phandle value."""
    controllers = []
    for node in sorted(dt.glob('soc/dcp@*')):
        handle = cells(node / 'phandle') or cells(node / 'linux,phandle')
        controllers.append({'path': '/' + str(node.relative_to(dt)),
                            'phandle': handle[0] if handle and len(handle) == 1 else None,
                            'tunnel': (node / 'apple,dp-tunnel').exists(),
                            'mux_controls': cells(node / 'mux-controls'),
                            'mux_index': cells(node / 'mux-index')})
    sources = []
    for prop in sorted(dt.glob('soc/**/apple,dp-source')):
        handles = cells(prop)
        matches = [c for c in controllers if handles and len(handles) == 1 and c['phandle'] == handles[0]]
        sources.append({'nhi': '/' + str(prop.parent.relative_to(dt)),
                        'dp_in_port': cells(prop.parent / 'apple,dp-in-port'),
                        'controller': matches[0] if len(matches) == 1 else None})
    return controllers, sources


def snapshot(sysroot, procroot, logs, log_source):
    dt = procroot / 'device-tree'
    controllers, sources = routing(dt)
    connectors = []
    for node in sorted((sysroot / 'class/drm').glob('card*-*')):
        if not EXTERNAL.fullmatch(node.name):
            continue
        try:
            edid = (node / 'edid').read_bytes()
        except OSError:
            edid = b''
        valid = (len(edid) >= 128 and len(edid) % 128 == 0
                 and edid[:8] == bytes.fromhex('00ffffffffffff00')
                 and len(edid) == (edid[126] + 1) * 128
                 and all(sum(edid[i:i + 128]) % 256 == 0 for i in range(0, len(edid), 128)))
        connectors.append({'name': node.name, 'status': text(node / 'status'),
                           'enabled': text(node / 'enabled'), 'modes': (text(node / 'modes') or '').splitlines(),
                           'edid_bytes': len(edid), 'edid_valid': bool(valid)})
    params = {name: text(sysroot / 'module/thunderbolt/parameters' / name)
              for name in ('allow_dp_tunnel', 'dprx_bypass', 'dprx_timeout')}
    active = [s for s in sources if s['controller'] and s['controller']['tunnel']]
    source_result = None
    if len(active) == 1 and logs is not None:
        address = active[0]['controller']['path'].rsplit('@', 1)[-1]
        # Only the mapped DCP's most recent completion counts, never built-in HDMI or an old success.
        for line in logs.splitlines():
            if re.search(r'\b' + re.escape(address) + r'\.dcp\b', line):
                match = SOURCE.search(line)
                if match:
                    waited, ret, rate, lanes = map(int, match.groups())
                    source_result = dict(waited=waited, ret=ret, rate=rate, lanes=lanes)
    linked = bool(source_result and source_result['ret'] == 0 and source_result['rate'] > 0
                  and source_result['lanes'] in (1, 2, 4) and source_result['waited'] > 0)
    # Logs cover the whole boot, not necessarily the current cable connection.
    return {'parameters': params, 'cmdline': text(procroot / 'cmdline'),
            'controllers': controllers, 'sources': sources, 'external_connectors': connectors,
            'log_source': log_source, 'logs_available': logs is not None,
            'latest_mapped_source_result': source_result,
            'link_configuration_observed': linked,
            'picture_verified': False,
            'qualification': 'Link logs are historical boot evidence. External connectors may belong to built-in HDMI; '
                             'correlate the dock route and EDID separately. A visible dock HDMI picture needs owner confirmation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sys-root', type=Path, default=Path('/sys'))
    parser.add_argument('--proc-root', type=Path, default=Path('/proc'))
    parser.add_argument('--log-file', type=Path, help='use a saved current-boot kernel log')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.log_file:
        logs, source = args.log_file.read_text(), str(args.log_file)
    else:
        logs, source = command(['journalctl', '-k', '-b', '--no-pager']), 'journalctl'
        if not logs or logs.strip() in ('-- No entries --', '-- No journal files were found. --'):
            logs, source = command(['dmesg']), 'dmesg'
        if not logs or not logs.strip():
            logs, source = None, 'unavailable'
    result = snapshot(args.sys_root, args.proc_root, logs, source)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print('== USB4 dock evidence (read-only) ==')
        print(json.dumps(result, indent=2))
        if logs is not None:
            print('\n== Recent DP-IN / DCP / tunnel log lines ==')
            lines = [line for line in logs.splitlines() if re.search(r'DPINDBG|DPTXPort|DPRX|DP tunnel|DP source', line, re.I)]
            print('\n'.join(lines[-50:]) or '(no relevant lines)')
        print('\nNo display success is inferred. Do not unplug a dock during an unbypassed DPRX read; '
              'see CONTROLLED-TEST.md and the recorded teardown hazard before any cable experiment.')


if __name__ == '__main__':
    main()
