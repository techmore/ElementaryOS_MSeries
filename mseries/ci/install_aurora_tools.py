#!/usr/bin/env python3
"""Bounded, signed Ubuntu ARM64 dependency downloads for ephemeral CI runners."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

MIRRORS = ('https://ports.ubuntu.com/ubuntu-ports', 'https://azure.archive.ubuntu.com/ubuntu')
PACKAGES = ('bc bison build-essential cpio flex libelf-dev libssl-dev pahole clang-22 llvm-22 '
            'lld-22 libclang-22-dev bindgen zstd device-tree-compiler kmod rsync').split()


def sources(codename, mirror):
    if not re.fullmatch(r'[a-z][a-z0-9]+', codename) or mirror not in MIRRORS:
        raise ValueError('Unsupported Ubuntu source')
    return (f'Types: deb\nURIs: {mirror}\nSuites: {codename} {codename}-updates '
            f'{codename}-backports {codename}-security\nComponents: main restricted universe multiverse\n'
            'Architectures: arm64\nSigned-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg\n')


def invoke(command):
    print('+ ' + ' '.join(command), flush=True)
    return subprocess.run(command, stdin=subprocess.DEVNULL, check=False,
                          env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}).returncode


def install(codename, architecture, root, run=invoke, packages=None):
    if architecture != 'arm64':
        raise ValueError('This installer is only for Ubuntu ARM64 CI')
    packages = tuple(PACKAGES if packages is None else packages)
    if not packages or any(not re.fullmatch(r'[a-z0-9][a-z0-9+.-]*', name) for name in packages):
        raise ValueError('Expected explicit Debian package names')
    root = Path(root)
    root.chmod(0o755)  # APT's unprivileged downloader must traverse its scratch directory.
    source_dir = root / 'sources'
    source_dir.mkdir()
    lists = root / 'lists'
    lists.mkdir()
    options = ['-o', 'Dir::Etc::sourcelist=/dev/null', '-o', f'Dir::Etc::sourceparts={source_dir}',
               '-o', f'Dir::State::lists={lists}', '-o', 'Acquire::Retries=1',
               '-o', 'Acquire::http::Timeout=30', '-o', 'Acquire::https::Timeout=30',
               '-o', 'APT::Update::Error-Mode=any', '-o', 'Dpkg::Use-Pty=0']
    apt = ['apt-get', *options]
    for mirror in MIRRORS:
        (source_dir / 'ubuntu.sources').write_text(sources(codename, mirror))
        print(f'Downloading signed dependencies from {mirror}', flush=True)
        if run(['timeout', '--kill-after=15s', '60', *apt, 'update']) != 0:
            continue
        # Bound the download, not dpkg: a slow mirror must never strand an install.
        if run(['timeout', '--kill-after=15s', '240', *apt, '--download-only', '--no-install-recommends',
                'install', '-y', *packages]) != 0:
            continue
        if run([*apt, '--no-download', '--no-install-recommends', 'install', '-y', *packages]) != 0:
            raise RuntimeError('Package installation failed after verified download')
        return
    raise RuntimeError('Both Ubuntu mirrors failed or exceeded the download time budget')


def main(packages=None):
    if os.environ.get('GITHUB_ACTIONS') != 'true' or os.geteuid() != 0:
        raise RuntimeError('Run as root only on an ephemeral GitHub Actions runner')
    release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if release.get('ID', '').strip('"') != 'ubuntu':
        raise RuntimeError('Ubuntu runner required')
    architecture = subprocess.check_output(['dpkg', '--print-architecture'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='aurora-apt-') as folder:
        install(release['VERSION_CODENAME'].strip('"'), architecture, folder, packages=packages)


if __name__ == '__main__':
    main()
