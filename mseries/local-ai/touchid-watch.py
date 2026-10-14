#!/usr/bin/python3
"""Exit 0 only when there is a new public sign of Linux Touch ID (Secure Enclave) support for M1 Macs.

Used as a precondition by mseries-verify. Looks at three places, at most every 6 hours (cached):
  1. omarchy-mac-pkgs' status page: does it still list Touch ID under "Not in the first release"?
  2. Asahi's M1 feature matrix: is the TouchID row still "TBA"?
  3. Commits on AsahiLinux/linux's fairydust branch (ahead of our kernel base) that mention the Secure
     Enclave, Touch ID or biometrics.
`--list` prints what it saw. Nothing here installs or enables anything.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = 'ce9f2eba72c0'  # fairydust commit our kernel is built from (same as upstream-watch.py)
STATUS_URL = 'https://raw.githubusercontent.com/omacom/omarchy-mac-pkgs/main/mac-manual/content/14-status.md'
MATRIX_URL = 'https://raw.githubusercontent.com/AsahiLinux/docs/main/docs/platform/feature-support/m1.md'
COMMITS_URL = 'https://api.github.com/repos/AsahiLinux/linux/compare/%s...fairydust?per_page=100' % BASE
PATTERN = re.compile(r'\bsep\b|secure[ -]enclave|touch[ -]?id|sbio|biometric|fingerprint', re.I)
CACHE = Path.home() / '.cache/mseries-touchid-watch.json'
REFRESH = 6 * 3600


def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'mseries-touchid-watch'})
    with urllib.request.urlopen(request, timeout=15) as response:
        return response.read().decode('utf-8', 'replace')


def fetch():
    seen, signals = [], []
    status = get(STATUS_URL)
    section = status.split('## Not in the first release', 1)[-1].split('\n## ', 1)[0] if '## Not in the first release' in status else ''
    listed = bool(re.search(r'touch id', section, re.I))
    seen.append('omarchy status: Touch ID %s under "Not in the first release"' % ('still listed' if listed else 'NOT listed'))
    if not listed:
        signals.append('omarchy-mac-pkgs status no longer lists Touch ID as not in the first release')
    matrix = get(MATRIX_URL)
    row = next((line for line in matrix.splitlines() if re.search(r'touch ?id', line, re.I)), '')
    tba = bool(re.search(r'\bTBA\b', row))
    seen.append('asahi M1 matrix row: %s' % (row.strip()[:120] or 'not found'))
    if row and not tba:
        signals.append('Asahi M1 feature matrix TouchID row changed: %s' % row.strip()[:120])
    data = json.loads(get(COMMITS_URL))
    hits = ['%s %s' % (c['sha'][:10], c['commit']['message'].splitlines()[0][:100])
            for c in data.get('commits', []) if PATTERN.search(c['commit']['message'].splitlines()[0])]
    seen.append('fairydust commits ahead of our base: %d, matching: %d' % (data.get('ahead_by', 0), len(hits)))
    signals.extend('fairydust commit: ' + hit for hit in hits)
    return {'checked': time.time(), 'seen': seen, 'signals': signals}


def main():
    try:
        cached = json.loads(CACHE.read_text())
    except (OSError, ValueError):
        cached = None
    if cached is None or time.time() - cached['checked'] > REFRESH:
        try:
            cached = fetch()
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cached))
        except (OSError, ValueError):
            if cached is None:
                return 1  # offline and nothing cached: not applicable
    if '--list' in sys.argv:
        print('\n'.join(cached['seen']))
        print('\n'.join(cached['signals']) or 'no new signs of Touch ID support')
    return 0 if cached['signals'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
