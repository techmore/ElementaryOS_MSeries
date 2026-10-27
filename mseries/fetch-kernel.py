#!/usr/bin/env python3
"""Fetch the pinned kernel packages from a Kernel-repo release and verify every checksum.

The OS image consumes kernel output by immutable release tag and sha256 (mseries/kernel-pin.json),
never by branch. `--check-profiles` only compares the pin with the Fairydust mkosi profile versions.
"""
import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PIN = ROOT / 'mseries/kernel-pin.json'
PROFILE = ROOT / 'mkosi.images/base/mkosi.profiles/fairydust/mkosi.conf'
SHA = re.compile(r'[0-9a-f]{64}')
BASE = 'https://github.com/{repo}/releases/download/{tag}/{asset}'


def load_pin(path=PIN):
    pin = json.loads(Path(path).read_text())
    tag = pin.get('release_tag', '')
    if pin.get('schema') != 1 or not tag.startswith('kernel-') or tag in ('latest', 'main', 'dev'):
        raise SystemExit('pin needs schema 1 and an immutable kernel-* release_tag')
    items = pin['packages'] + [pin['boot']['m1n1_bootbin']]
    for item in items:
        if not SHA.fullmatch(item.get('sha256', '')) or not item.get('asset') or not item.get('file'):
            raise SystemExit(f'pin entry is missing sha256, asset or file: {item}')
    return pin, items


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def profile_versions(path=PROFILE):
    out = {}
    for line in Path(path).read_text().splitlines():
        m = re.fullmatch(r'\s+([A-Za-z0-9.+-]+)=(\S+)', line)
        if m:
            out[m[1]] = m[2]
    return out


def check_profiles(pin, path=PROFILE):
    have = profile_versions(path)
    bad = [f"{p['name']}: pin {p['version']} profile {have.get(p['name'])}"
           for p in pin['packages'] if have.get(p['name']) != p['version']]
    if bad:
        raise SystemExit('fairydust profile does not match kernel-pin.json:\n  ' + '\n  '.join(bad))


def fetch(pin, items, out, base):
    out.mkdir(parents=True, exist_ok=True)
    for item in items:
        url = base.format(repo=pin['kernel_repo'], tag=pin['release_tag'], asset=item['asset'])
        with urllib.request.urlopen(url) as r:
            data = r.read()
        if sha256(data) != item['sha256']:
            raise SystemExit(f"checksum mismatch for {item['file']}: got {sha256(data)}, pinned {item['sha256']}")
        (out / item['file']).write_bytes(data)
        print(f"ok {item['file']}")
    debs = [p for p in pin['packages']]
    upstream = [p for p in debs if not p['name'].startswith('linux-image-')]
    boot = pin['boot']['m1n1_bootbin']
    line = lambda i: f"{i['sha256']}  {i['file']}\n"
    (out / 'SHA256SUMS').write_text(''.join(line(p) for p in debs))
    (out / 'UPSTREAM-SHA256SUMS').write_text(''.join(line(p) for p in upstream))
    (out / 'FAIRYDUST-BOOT-SHA256SUMS').write_text(line(boot))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pin', default=str(PIN))
    ap.add_argument('--out', type=Path)
    ap.add_argument('--base-url', default=BASE, help='template with {repo} {tag} {asset}; file:// works for tests')
    ap.add_argument('--check-profiles', action='store_true')
    a = ap.parse_args()
    pin, items = load_pin(a.pin)
    if a.check_profiles:
        check_profiles(pin)
        print('pin matches fairydust profile versions')
    if a.out:
        fetch(pin, items, a.out, a.base_url)
    return 0


if __name__ == '__main__':
    sys.exit(main())
