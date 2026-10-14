#!/bin/bash
# Put the usb4.4 kernel's t6000-j314s device tree into /boot/m1n1/boot.bin (this M1 Pro 14").
# m1n1, U-Boot and every other DTB stay byte-identical (see swap-dtb.py). boot.bin runs BEFORE GRUB, so a bad
# one stops every OS from booting: this script backs it up first and verifies the result before replacing.
#
#   sudo bash install-bootbin.sh [artifact-dir]            # dry run: builds + verifies a staged image, changes nothing
#   sudo bash install-bootbin.sh [artifact-dir] --apply    # replaces /boot/m1n1/boot.bin
#
# Rollback if the Mac stops before GRUB: macOS recovery steps in RECOVERY.md, copy boot.bin.KNOWN-GOOD-pre-dtb-*.
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
art=; apply=0
for a in "$@"; do case $a in --apply) apply=1 ;; *) art=$a ;; esac; done
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
home=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)
art=${art:-$home/mseries-kernel-usb4.4}
deb=$(ls "$art"/linux-image-*usb4*.deb 2>/dev/null | head -1) || true
[[ -n $deb ]] || { echo "no linux-image-*usb4*.deb in $art" >&2; exit 1; }
cur=/boot/m1n1/boot.bin
[[ -f $cur ]] || { echo "$cur not found; is the ESP mounted at /boot?" >&2; exit 1; }
grep -qa 'apple,j314s' "$cur" || { echo "$cur has no j314s device tree; refusing" >&2; exit 1; }

tmp=$(mktemp -d /var/tmp/usb4-bootbin.XXXXXX); trap 'rm -rf "$tmp"' EXIT
dpkg-deb -x "$deb" "$tmp/pkg"
dtb=$(ls "$tmp"/pkg/usr/lib/linux-image-*/apple/t6000-j314s.dtb)
echo "== building staged image"
python3 -I "$here/swap-dtb.py" --in "$cur" --dtb "$dtb" --match apple,j314s --out "$tmp/boot.bin.new"
new=$tmp/boot.bin.new
echo "== checks"
python3 -I "$here/swap-dtb.py" --in "$new" --dtb "$dtb" --match apple,j314s --check | grep -q 'identical to input' \
  || { echo "staged image does not contain the new tree" >&2; exit 1; }
grep -qa 'usb4-0-acio' "$new" || { echo "staged image has no USB4 nodes" >&2; exit 1; }
[[ $(stat -c %s "$new") -lt $((15*1024*1024)) ]] || { echo "staged image is unexpectedly large" >&2; exit 1; }
echo "ok: contains the new j314s tree with USB4 nodes; m1n1/U-Boot unchanged"
df -h /boot | tail -1

if (( ! apply )); then
  echo; echo "DRY RUN: nothing changed. Re-run with --apply to replace $cur."
  exit 0
fi
stamp=$(date +%Y%m%d-%H%M%S)
echo "== backup"
cp -a "$cur" "/boot/m1n1/boot.bin.KNOWN-GOOD-pre-dtb-$stamp"
install -d /root/usb4-backup; cp -a "$cur" "/root/usb4-backup/boot.bin.pre-dtb-$stamp"
echo "== install (write beside, verify, rename)"
cp "$new" /boot/m1n1/boot.bin.new
sync
cmp "$new" /boot/m1n1/boot.bin.new
mv -f /boot/m1n1/boot.bin.new "$cur"
sync
cmp "$new" "$cur" && echo "installed and verified: $cur"
echo "Backups: /boot/m1n1/boot.bin.KNOWN-GOOD-pre-dtb-$stamp and /root/usb4-backup/boot.bin.pre-dtb-$stamp"
echo "Reboot into the usb4 TEST entry. If the Mac stops before GRUB, see RECOVERY.md."
