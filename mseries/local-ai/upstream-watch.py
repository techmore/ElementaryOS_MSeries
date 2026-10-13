#!/usr/bin/python3
"""Exit 0 only when AsahiLinux/linux's fairydust branch has new commits about DisplayPort/USB4 work.

Used as a precondition by mseries-verify. Polls GitHub at most every 6 hours (cached), so the 10-minute
timer is cheap. Baseline is the fairydust commit our kernel is built from. `--list` prints the matches.
"""
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

BASE = 'ce9f2eba72c0'  # fairydust commit mseries/fairydust/usb4 is built on
PATTERN = re.compile(r'dp[ -]?(in|tunnel|alt)|dptx|dpin|tunnel|usb4|thunderbolt|acio|atc|dcpext|xbar', re.I)
CACHE = Path.home() / '.cache/mseries-upstream-watch.json'
URL = 'https://api.github.com/repos/AsahiLinux/linux/compare/%s...fairydust?per_page=100'
REFRESH = 6 * 3600


def fetch():
    request = urllib.request.Request(URL % BASE, headers={'User-Agent': 'mseries-upstream-watch'})
    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.load(response)
    hits = [f"{c['sha'][:10]} {c['commit']['message'].splitlines()[0][:100]}"
            for c in data.get('commits', []) if PATTERN.search(c['commit']['message'].splitlines()[0])]
    return {'checked': time.time(), 'ahead': data.get('ahead_by', 0), 'hits': hits}


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
        print(f"fairydust is {cached['ahead']} commits ahead of our base")
        print('\n'.join(cached['hits']) or 'no matching commits')
    return 0 if cached['hits'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
