#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reproduce/fix empty standby signature export in small regular-file images.

Uses synthetic root-owned data only, never a real disk or installed system.
Active verity hashing/signing stays enabled in both cases.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
SPARES = ['20-usr-verify-sig-bside.conf', '21-usr-verity-bside.conf', '22-usr-bside.conf']


def run(command, **kwargs):
    return subprocess.run(command, text=True, capture_output=True, env=dict(os.environ, SOURCE_DATE_EPOCH="0"), **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repart', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('new fixture directory required')
    args.output.mkdir(mode=0o700, parents=True)
    root = args.output.resolve()
    tree = root / 'tree'
    for name in ['usr', 'efi', 'boot']:
        (tree / name).mkdir(parents=True)
    (tree / 'usr/fixture').write_text('signed elementary research fixture\n')
    for path in [*tree.rglob('*'), tree]:
        os.utime(path, (0, 0))
    key, certificate = root / 'key.pem', root / 'certificate.pem'
    cert = run(['openssl', 'req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes',
                '-subj', '/CN=M4-Repart-Fixture', '-days', '1', '-keyout', str(key), '-out', str(certificate)])
    if cert.returncode:
        raise RuntimeError(cert.stderr)
    key.chmod(0o600)
    results = {}
    images = {}
    for case in ['default-spares', 'no-spare-splits']:
        definitions = root / case
        definitions.mkdir()
        for file in (REPO / 'mkosi.images/sysupdate/mkosi.repart').glob('*.conf'):
            text = file.read_text().replace('1.5G', '64M').replace('7G', '32M').replace('400M', '4M')
            if file.name in SPARES:
                text = '\n'.join(line for line in text.splitlines() if not line.startswith('SplitName=')) + '\n'
                if case == 'no-spare-splits':
                    text += 'SplitName=-\n'
            (definitions / file.name).write_text(text)
        image = root / (case + '.raw')
        command = ['unshare', '--user', '--map-root-user', str(args.repart.resolve()),
                   '--empty=create', '--size=auto', '--dry-run=no', '--offline=yes', '--split=no',
                   '--seed=8a0e9ade-383d-4c42-b412-ad6fe4a2b3ba', '--root=' + str(tree),
                   '--definitions=' + str(definitions), '--certificate=' + str(certificate),
                   '--private-key=' + str(key), str(image)]
        created = run(command)
        if created.returncode:
            (root / (case + '.log')).write_text(created.stdout + created.stderr)
            raise ValueError('fixture creation failed; inspect log')
        command[command.index('--empty=create')] = '--empty=allow'
        command[command.index('--split=no')] = '--split=yes'
        result = run(command)
        (root / (case + '.log')).write_text(created.stdout + created.stderr + result.stdout + result.stderr)
        results[case] = result.returncode
        images[case] = image
        if case == 'default-spares':
            if result.returncode == 0 or 'Verity signature partition is empty' not in result.stderr:
                raise ValueError('did not reproduce the expected empty-spare extraction failure; inspect log')
        elif result.returncode:
            raise ValueError('fixed split failed; inspect log: ' + result.stderr[-1200:])
    spec = importlib.util.spec_from_file_location('gpt', HERE / 'export-partitions.py')
    gpt = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gpt)
    tables = []
    for image in images.values():
        with image.open('rb') as stream:
            tables.append(gpt.inspect(stream, image.stat().st_size)[3])
    # Label/type/UUID/geometry/attributes are data-plane metadata, not export policy.
    if tables[0] != tables[1]:
        raise ValueError('split policy unexpectedly changed GPT metadata')
    good = root / 'no-spare-splits.raw'
    for name in ['usr-arm64', 'usr-arm64-verity', 'usr-arm64-verity-sig']:
        if (root / ('no-spare-splits.' + name + '.raw')).exists():
            raise ValueError('an empty standby split artifact was still exported')
    signature_file = next(root.glob('no-spare-splits.usr-arm64-verity-sig.*.raw'))
    data_file = next(root.glob('no-spare-splits.usr-arm64.*.raw'))
    hash_file = next(root.glob('no-spare-splits.usr-arm64-verity.*.raw'))
    signature = json.loads(signature_file.read_bytes().rstrip(b'\0'))
    signature_der = root / 'signature.der'
    signature_der.write_bytes(base64.b64decode(signature['signature'], validate=True))
    content = root / 'root-hash.txt'
    content.write_text(signature['rootHash'])
    verify = run(['openssl', 'cms', '-verify', '-binary', '-inform', 'DER', '-in', str(signature_der),
                  '-content', str(content), '-CAfile', str(certificate), '-purpose', 'any', '-out', str(root / 'verified-hash')])
    if verify.returncode:
        raise ValueError('active signature verification failed: ' + verify.stderr)
    verity = run(['veritysetup', 'verify', str(data_file), str(hash_file), signature['rootHash']])
    if verity.returncode:
        raise ValueError('active data/hash verification failed: ' + verity.stderr)
    (root / 'receipt.json').write_text(json.dumps({
        'scope': 'small GPT/erofs/verity regular-file fixture; no full image or hardware result',
        'repart_version': run([str(args.repart.resolve()), '--version']).stdout.splitlines()[0],
        'case_exit_codes': results, 'gpt_metadata_identical': True,
        'partitions': tables[1], 'active_signature_verified': True, 'active_data_hash_verified': True,
        'standby_slots_retained': True, 'standby_split_exports_disabled': True,
        'root_hash': signature['rootHash'], 'hardware_validated': False,
    }, indent=2) + '\n')
    print('Empty-standby failure reproduced; split fix preserves GPT and active verified verity')


if __name__ == '__main__':
    main()
