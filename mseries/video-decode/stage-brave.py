#!/usr/bin/env python3
"""Stage the official, pinned ARM64 Brave runtime inside the immutable /usr tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def stage(destination, package=None, pin_path=None):
    pin_path = Path(pin_path) if pin_path else Path(__file__).with_name('brave-factory.json')
    pin = json.loads(pin_path.read_text())
    destination = Path(destination)
    runtime = destination / 'usr/lib/mseries-brave'
    if runtime.exists():
        raise ValueError('Brave runtime already exists; refusing to merge versions')
    with tempfile.TemporaryDirectory(prefix='mseries-brave-') as temp:
        work = Path(temp)
        if package:
            archive = Path(package)
        else:
            archive = work / 'brave.deb'
            with urllib.request.urlopen(pin['url'], timeout=120) as response, archive.open('wb') as out:
                shutil.copyfileobj(response, out)
        if digest(archive) != pin['sha256']:
            raise ValueError('Brave package checksum mismatch')
        for field, expected in [('Package', 'brave-browser'), ('Version', pin['version']),
                                ('Architecture', pin['architecture'])]:
            actual = subprocess.check_output(['dpkg-deb', '-f', str(archive), field], text=True).strip()
            if actual != expected:
                raise ValueError(f'Unexpected Brave {field}: {actual}')
        extracted = work / 'package'
        subprocess.run(['dpkg-deb', '-x', str(archive), str(extracted)], check=True)
        source = extracted / 'opt/brave.com/brave'
        # Keep all vendor data and licenses; run no package maintainer scripts.
        runtime.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, runtime, symlinks=True)
        doc = destination / 'usr/share/doc/mseries-brave'
        doc.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source / 'LICENSE', doc / 'LICENSE')
        shutil.copy2(pin_path, doc / 'pin.json')
        (doc / 'SOURCE').write_text(
            f"Official Brave binary: {pin['url']}\nSHA256: {pin['sha256']}\n"
            f"Source: https://github.com/brave/brave-browser/tree/v{pin['version']}\n"
            'License: MPL-2.0; vendor LICENSE retained; third-party notices: brave://credits\n'
            'Relocated from /opt/brave.com/brave to /usr/lib/mseries-brave.\n'
            'Updates: rebuild the image with a reviewed version and SHA256 pin.\n')
        files = {p.relative_to(runtime).as_posix(): digest(p)
                 for p in sorted(runtime.rglob('*')) if p.is_file()}
        (doc / 'files.json').write_text(json.dumps(files, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', required=True)
    parser.add_argument('--package', default=os.environ.get('MSERIES_BRAVE_DEB'))
    args = parser.parse_args()
    stage(args.dest, args.package)
