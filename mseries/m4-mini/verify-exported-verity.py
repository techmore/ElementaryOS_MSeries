#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verify active exported M4 usr data/hash/signature; never mount or install.

The embedded certificate proves internal signature consistency, not external
signer trust, Apple authorization, enrollment or native boot acceptance.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import stat
import subprocess

TYPES = {
    'signature': 'c23ce4ff-44bd-4b00-b2d4-b41b3419e02a',
    'hash': '6e11a4e7-fbca-4ded-b9e9-e1a512bb664e',
    'data': 'b0e01050-ee5f-4390-949a-9101b17104e9',
}


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--export', dest='export', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists() or (args.export / 'INCOMPLETE').exists():
        raise ValueError('new output and complete export required')
    manifest = json.loads((args.export / 'manifest.json').read_text())
    payloads = {}
    for kind, guid in TYPES.items():
        matches = [p for p in manifest['partitions'] if p['type_guid'] == guid and 'payload' in p]
        if len(matches) != 1:
            raise ValueError('export exactly one active ' + kind + ' payload')
        part = matches[0]
        name = part['payload']['file']
        if Path(name).name != name:
            raise ValueError('payload must be a basename')
        path = args.export / name
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_size != part['size_bytes']:
            raise ValueError('regular correctly sized payload required')
        if digest(path) != part['payload']['sha256']:
            raise ValueError('payload hash differs from export: ' + kind)
        payloads[kind] = path.resolve()
    if payloads['signature'].stat().st_size > 1024 * 1024:
        raise ValueError('signature partition exceeds this profile limit')
    signature = json.loads(payloads['signature'].read_bytes().rstrip(b'\0'))
    for key in ['rootHash', 'certificateFingerprint']:
        if not isinstance(signature.get(key), str) or not re.fullmatch('[0-9a-f]{64}', signature[key]):
            raise ValueError('SHA256 ' + key + ' required')
    der = base64.b64decode(signature['signature'], validate=True)
    args.output.mkdir(parents=True)
    root = args.output.resolve()
    marker = root / 'INCOMPLETE'
    marker.touch()
    (root / 'signature.der').write_bytes(der)
    (root / 'root-hash.txt').write_text(signature['rootHash'], encoding='ascii')

    def run(command):
        result = subprocess.run(command, capture_output=True)
        with (root / 'commands.log').open('ab') as log:
            log.write((' '.join(map(str, command)) + '\n').encode())
            log.write(result.stderr)
        if result.returncode:
            raise ValueError('verification command failed: ' + str(command[0]))
        return result.stdout

    certs = run(['openssl', 'pkcs7', '-inform', 'DER', '-in', str(root / 'signature.der'), '-print_certs'])
    blocks = re.findall(rb'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', certs, re.S)
    matching = []
    for index, block in enumerate(blocks):
        path = root / f'certificate-{index}.pem'
        path.write_bytes(block + b'\n')
        cert_der = run(['openssl', 'x509', '-in', str(path), '-outform', 'DER'])
        if hashlib.sha256(cert_der).hexdigest() == signature['certificateFingerprint']:
            matching.append(path)
    if len(matching) != 1:
        raise ValueError('exactly one embedded certificate must match the fingerprint')
    run(['openssl', 'cms', '-verify', '-binary', '-inform', 'DER', '-in', str(root / 'signature.der'),
         '-content', str(root / 'root-hash.txt'), '-CAfile', str(matching[0]), '-purpose', 'any',
         '-out', str(root / 'verified-hash')])
    if (root / 'verified-hash').read_bytes() != signature['rootHash'].encode('ascii'):
        raise ValueError('verified signature content differs from root hash')
    run(['veritysetup', 'verify', str(payloads['data']), str(payloads['hash']), signature['rootHash']])
    (root / 'receipt.json').write_text(json.dumps({
        'scope': 'active exported regular-file data/hash/signature consistency; no mount, installation or boot',
        'source_image_sha256': manifest['source_sha256'],
        'source_image_size': manifest['source_size_bytes'],
        'root_hash': signature['rootHash'], 'certificate_fingerprint_sha256': signature['certificateFingerprint'],
        'payload_sha256': {kind: digest(path) for kind, path in payloads.items()},
        'embedded_certificate_fingerprint_matches': True, 'signature_verified': True,
        'data_hash_verified': True,
        'trust_scope': 'certificate embedded in the research signature; external signer trust is not established',
        'external_signer_trust_verified': False, 'native_trust_enrolled': False,
        'installer_admission': False, 'hardware_validated': False,
    }, indent=2) + '\n')
    marker.unlink()
    print('Active signature and data/hash verify; external trust and hardware remain unqualified')


if __name__ == '__main__':
    main()
