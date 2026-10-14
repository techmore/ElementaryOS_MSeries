#!/bin/bash
# Build the pinned m1n1 natively on this (aarch64) Mac, no sudo, no chroot. Installs rustup for the user.
set -euo pipefail
SHA=${M1N1_SHA:-57a9339ffd1876e78297b17d34dece8cff8fa1ba}; D=$HOME/m1n1-build
command -v rustup >/dev/null || curl -fsSL https://sh.rustup.rs | sh -s -- -y --profile minimal -t aarch64-unknown-none-softfloat
. "$HOME/.cargo/env"; rustup target add aarch64-unknown-none-softfloat
mkdir -p "$D"; cd "$D"
[ -d m1n1 ] || { curl -fL -o m1n1.tgz "https://codeload.github.com/AsahiLinux/m1n1/tar.gz/$SHA"; mkdir m1n1; tar xzf m1n1.tgz -C m1n1 --strip-components=1; }
make -C m1n1 ARCH= RELEASE=1 -j"$(nproc)"
ls -la m1n1/build/m1n1.bin; echo -n "tunable-rc strings: "; strings -n 6 m1n1/build/m1n1.bin | grep -c apple,tunable-rc
