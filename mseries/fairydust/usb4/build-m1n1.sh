#!/bin/bash
# Build current AsahiLinux/m1n1 (has ACIO/USB4 tunable + DROM support) in the Arch chroot. Builds only; installs nothing.
set -euo pipefail
R=/mnt/fdbuild/root; D=/home/techmore/m1n1-build
SHA=${M1N1_SHA:-57a9339f}
mountpoint -q $R || mount -o subvol=@ /dev/mapper/root $R
for m in dev proc sys; do mountpoint -q $R/$m || mount --bind /$m $R/$m; done
mountpoint -q $R/run  || mount -t tmpfs -o mode=755 tmpfs $R/run
mountpoint -q $R/home || mount -o subvol=@home /dev/mapper/root $R/home
install -d -o 1001 -g 1001 $R$D
cat > $R$D/go.sh <<'EOS'
set -euo pipefail
cd /home/techmore/m1n1-build
if [ ! -d m1n1 ]; then
  curl -fL --retry 5 -o m1n1.tar.gz "https://codeload.github.com/AsahiLinux/m1n1/tar.gz/main"
  mkdir m1n1 && tar xzf m1n1.tar.gz -C m1n1 --strip-components=1
fi
cd m1n1
export PATH="$HOME/.cargo/bin:$PATH"
rustup toolchain list || true
make ARCH= RELEASE=1 -j10 2>&1 | tail -25
ls -la build/m1n1.bin
strings -n 6 build/m1n1.bin | grep -E "^v1\.|##m1n1_ver##" | head -2
echo -n "tunable-rc support strings: "; strings -n 6 build/m1n1.bin | grep -c "apple,tunable-rc" || true
echo M1N1_BUILD_DONE
EOS
chown 1001:1001 $R$D/go.sh
chroot $R runuser -l techmore -c "bash $D/go.sh"
