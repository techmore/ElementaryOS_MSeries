#!/usr/bin/python3
"""Exercise the real troubleshooting client with a synthetic log and private report."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    fixture = '[1] wifi: firmware loaded successfully\n[2] panel: process exited with SIGSEGV\n'
    with tempfile.TemporaryDirectory(prefix='mseries-triage-eval-') as root:
        path = Path(root) / 'synthetic.log'; path.write_text(fixture)
        result = subprocess.run([sys.executable, str(Path(__file__).with_name('troubleshoot.py')),
                                 '--start', '--release-model', '--file', str(path),
                                 'Explain what this excerpt establishes. Does it prove a Wi-Fi failure?'],
                                capture_output=True, text=True, timeout=600)
    match = re.search(r'Saved locally: (.+)', result.stdout)
    report_mode = stat.S_IMODE(Path(match.group(1)).stat().st_mode) if match else None
    answer = result.stdout.split('\nSaved locally:')[0]
    receipt = {'fixture': fixture, 'fixture_sha256': hashlib.sha256(fixture.encode()).hexdigest(),
               'exit_code': result.returncode, 'private_report_mode': report_mode,
               'answer': answer, 'scope': 'synthetic chosen-file path through the production CLI; no real journal input'}
    receipt['passed'] = result.returncode == 0 and report_mode == 0o600 and bool(re.search(r'panel|SIGSEGV', answer, re.I))
    # This smoke proves transport/reporting, not comprehensive diagnostic
    # accuracy. The full synthetic answer is reviewable.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n')
    if not receipt['passed']:
        raise SystemExit('Synthetic troubleshooting smoke did not complete successfully')
    print('Synthetic troubleshooting client/report test passed.')


if __name__ == '__main__':
    main()
