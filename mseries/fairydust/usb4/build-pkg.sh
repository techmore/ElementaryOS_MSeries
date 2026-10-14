#!/bin/bash
# Build (only) the linux-asahi-fairydust-usb4 package inside the Arch (@) chroot, run from elementary.
# Does NOT install anything and does NOT touch /boot. Run as root: sudo ./build-pkg.sh
# Needs: ./config (zcat /proc/config.gz > config), PKGBUILD and the 0001-*.patch in this directory.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ -f $here/config ]] || zcat /proc/config.gz > "$here/config"
R=/mnt/fdbuild/root; D=/home/techmore/usb4-pkg
mkdir -p $R
mountpoint -q $R      || mount -o subvol=@ /dev/mapper/root $R
for m in dev proc sys; do mountpoint -q $R/$m || mount --bind /$m $R/$m; done
mountpoint -q $R/run  || mount -t tmpfs -o mode=755 tmpfs $R/run
mountpoint -q $R/home || mount -o subvol=@home /dev/mapper/root $R/home
install -d -o 1001 -g 1001 $R$D
cp "$here"/PKGBUILD "$here"/config "$here"/0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch $R$D/
cp "$here"/../debian/0003-avd-job-segments-use-kvmalloc.patch $R$D/0002-avd-job-segments-use-kvmalloc.patch   # the one canonical copy
chown -R 1001:1001 $R$D
chroot $R runuser -l techmore -c "cd $D && makepkg --cleanbuild --force --noconfirm --nodeps"
ls -la $R$D/*.pkg.tar.* && echo BUILD_PKG_DONE
