#!/bin/bash
# Put the usb4.4 kernel's modules in the running system so the TEST boot entry can mount /boot.
#   sudo bash install-modules.sh [artifact-dir]     (default: ~/mseries-kernel-usb4.4)
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
home=${SUDO_USER:+$(getent passwd "$SUDO_USER" | cut -d: -f6)}
art=${1:-${home:-$HOME}/mseries-kernel-usb4.4}
deb=$(ls "$art"/linux-image-*usb4*.deb 2>/dev/null | head -1) || true
[[ -n $deb ]] || { echo "no linux-image-*usb4*.deb in $art" >&2; exit 1; }
kv=7.1.13-elementary-fairydust-usb4
tmp=$(mktemp -d /var/tmp/usb4-mods.XXXXXX); trap 'rm -rf "$tmp"' EXIT
echo "unpacking $deb"
dpkg-deb -x "$deb" "$tmp"
[[ -d $tmp/lib/modules/$kv ]] || { echo "package has no modules for $kv" >&2; exit 1; }
echo "copying modules to /usr/lib/modules/$kv"
rm -rf "/usr/lib/modules/$kv"
cp -a "$tmp/lib/modules/$kv" "/usr/lib/modules/$kv"
depmod -a "$kv"
find "/usr/lib/modules/$kv" -name 'nls_iso8859-1.ko*' | grep -q . || { echo "FAILED: nls_iso8859-1 missing" >&2; exit 1; }
echo "OK: $(find /usr/lib/modules/$kv -name '*.ko*' | wc -l) modules installed, nls_iso8859-1 present."
echo "Now reboot and choose 'elementary OS (M-series, fairydust + USB4 test)'."
