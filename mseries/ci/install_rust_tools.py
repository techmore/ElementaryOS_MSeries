#!/usr/bin/env python3
"""Install signed Rust-lane test dependencies on ephemeral Ubuntu ARM64 CI."""

import install_aurora_tools as shared


PACKAGES = (
    'build-essential cargo rustc rustfmt rust-clippy sqlite3 dbus-daemon '
    'libglib2.0-bin libglib2.0-dev pkg-config debhelper dpkg-dev fakeroot '
    'debootstrap gpgv python3-apt python3-yaml'
).split()


def main():
    shared.main(packages=PACKAGES)


if __name__ == '__main__':
    main()
