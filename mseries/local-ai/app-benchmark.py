#!/usr/bin/python3
"""Measure real MCP app-adapter responses without publishing app contents."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--label', required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    report = {'label': args.label, 'method': 'Real stdio MCP, three sequential read-only adapter calls per surface. Backend response latency, not GUI frame latency. No private contents published.', 'calls': []}
    with tempfile.TemporaryDirectory(prefix='mseries-app-eval-') as root:
        (Path(root) / 'Test.md').write_text('Synthetic adapter latency test')
        child = subprocess.Popen(['/usr/bin/python3', str(Path(__file__).with_name('os-mcp.py'))],
                                 env=dict(os.environ, MSERIES_ASSISTANT_WORKSPACE=root),
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        sequence = 0
        def rpc(method, params):
            nonlocal sequence
            sequence += 1
            started = time.monotonic()
            child.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': sequence, 'method': method, 'params': params}) + '\n'); child.stdin.flush()
            # A local adapter could hang (e.g. a stalled EDS). Bound the read.
            import select
            if not select.select([child.stdout], [], [], 30)[0]:
                raise TimeoutError('MCP adapter exceeded thirty seconds')
            response = json.loads(child.stdout.readline())
            if 'error' in response:
                raise RuntimeError('MCP protocol error')
            return response['result'], time.monotonic() - started
        try:
            rpc('initialize', {'protocolVersion': '2025-03-26'})
            for repeat in range(3):
                for name, params in [('system_status', {}), ('list_apps', {}), ('list_tasks', {}),
                                     ('list_calendar_events', {}), ('get_energy', {'window': 'now'}),
                                     ('recent_faults', {}), ('workspace_list_files', {}),
                                     ('workspace_read_file', {'path': 'Test.md'})]:
                    result, elapsed = rpc('tools/call', {'name': name, 'arguments': params})
                    row = {'tool': name, 'repeat': repeat + 1, 'elapsed_s': elapsed, 'transport_ok': not result.get('isError', False)}
                    if row['transport_ok']:
                        value = json.loads(result['content'][0]['text'])
                        for key in ['tasks', 'events', 'apps', 'files', 'errors']:
                            if isinstance(value.get(key), list):
                                row[key + '_count'] = len(value[key])
                        for key in ['available', 'stale', 'fresh', 'source']:
                            if key in value and isinstance(value[key], (bool, type(None))):
                                row[key] = value[key]
                    report['calls'].append(row)
        finally:
            child.stdin.close()
            try: child.wait(timeout=3)
            except subprocess.TimeoutExpired: child.kill(); child.wait()
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + '\n')
    print('Saved bounded app-adapter timings; private app contents excluded.')


if __name__ == '__main__':
    main()
