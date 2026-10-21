#!/usr/bin/env bash
# Build machine-lab_<version>_<arch>.deb from this source tree.
#   bash mseries/machine-lab/build-deb.sh            # writes build/machine-lab-deb/*.deb
# Needs: meson, valac, libgtk-4-dev, libgranite-7-dev, dpkg-deb.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$here/../.." && pwd)"
out="${MACHINE_LAB_OUTPUT_DIR:-$repo_root/build/machine-lab-deb}"
stage="$out/package"
work="$out/meson"

for tool in meson ninja valac dpkg-deb; do
  command -v "$tool" >/dev/null || { echo "Missing build tool: $tool" >&2; exit 2; }
done

version="$(grep -m1 -oP "version: '\K[0-9.]+" "$here/meson.build")"
arch="$(dpkg --print-architecture)"
debver="${version}-1~mseries1"

rm -rf "$out"
mkdir -p "$stage"
meson setup "$work" "$here" --prefix=/usr --buildtype=release >/dev/null
meson compile -C "$work"
meson test -C "$work" --print-errorlogs
DESTDIR="$stage" meson install -C "$work" >/dev/null

# Rename the launcher helpers' tests/build artefacts out of the package (none are installed) and fix modes.
find "$stage" -type d -exec chmod 0755 {} +

installed_kb="$(du -sk "$stage" | cut -f1)"
install -d "$stage/DEBIAN"
cat >"$stage/DEBIAN/control" <<CONTROL
Package: machine-lab
Version: $debver
Section: utils
Priority: optional
Architecture: $arch
Installed-Size: $installed_kb
Depends: libgtk-4-1 (>= 4.12), libgranite-7-7 | libgranite7, libjson-glib-1.0-0, qemu-system-arm, qemu-utils, qemu-efi-aarch64, python3
Recommends: swtpm, genisoimage, curl, openssl, incus, qemu-system-x86, ovmf, xz-utils, zstd, unzip
Maintainer: elementaryos-mseries local build
Homepage: https://github.com/techmore/ElementaryOS_MSeries
Description: Native elementary OS virtual machine app (ARM64)
 Machine Lab creates and runs ARM64 virtual machines with QEMU/KVM: a Display
 tab with full screen, mouse and keyboard, pause and resume, a live console,
 readiness and disk-space checks, and import of mseries-vm guests.
CONTROL

cat >"$stage/DEBIAN/postinst" <<'POST'
#!/bin/sh
set -e
command -v update-desktop-database >/dev/null && update-desktop-database -q /usr/share/applications || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor || true
exit 0
POST
cp "$stage/DEBIAN/postinst" "$stage/DEBIAN/postrm"
chmod 0755 "$stage/DEBIAN/postinst" "$stage/DEBIAN/postrm"

pkg="$out/machine-lab_${debver}_${arch}.deb"
dpkg-deb --root-owner-group --build "$stage" "$pkg" >/dev/null
echo "Built $pkg"
dpkg-deb --info "$pkg" | sed -n '1,14p'
dpkg-deb --contents "$pkg" | awk '{print $1, $3, $6}' | sed -n '1,40p'
