#!/bin/bash
# Put a newer m1n1 (one that generates apple,tunable-rc/-nhi + thunderbolt-drom for the USB4 dock Ethernet)
# at the front of /boot/m1n1/boot.bin. DTBs and U-Boot stay byte-identical (swap-m1n1.py). boot.bin runs
# BEFORE GRUB: this backs it up first, verifies the staged image, and only then replaces it.
#
#   bash build-m1n1-local.sh                                        # (no sudo) builds ~/m1n1-build/m1n1/build/m1n1.bin
#   sudo bash install-m1n1-bootbin.sh [m1n1.bin]            # dry run
#   sudo bash install-m1n1-bootbin.sh [m1n1.bin] --apply
# Rollback: macOS recovery per RECOVERY.md; copy boot.bin.KNOWN-GOOD-pre-m1n1-* (or the earlier pre-dtb one).
set -euo pipefail
here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
m1n1=; apply=0
for a in "$@"; do case $a in --apply) apply=1 ;; *) m1n1=$a ;; esac; done
[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
home=$(getent passwd "${SUDO_USER:-root}" | cut -d: -f6)
m1n1=${m1n1:-$home/m1n1-build/m1n1/build/m1n1.bin}
cur=/boot/m1n1/boot.bin
[[ -f $m1n1 && -f $cur ]] || { echo "missing $m1n1 or $cur" >&2; exit 1; }
grep -qa 'apple,j314s' "$cur" || { echo "$cur has no j314s tree; refusing" >&2; exit 1; }
grep -qa 'apple,tunable-rc' "$m1n1" || { echo "$m1n1 lacks tunable-rc support; refusing" >&2; exit 1; }
tmp=$(mktemp -d /var/tmp/m1n1-bootbin.XXXXXX); trap 'rm -rf "$tmp"' EXIT
python3 -I "$here/swap-m1n1.py" --in "$cur" --m1n1 "$m1n1" --out "$tmp/new"
sz=$(stat -c %s "$tmp/new"); (( sz < 15*1024*1024 )) || { echo "image too large: $sz" >&2; exit 1; }
grep -qa 'apple,j314s' "$tmp/new" && grep -qa 'usb4-0-acio' "$tmp/new" || { echo "staged image lost the j314s usb4 tree" >&2; exit 1; }
echo "staged OK ($sz bytes)"
(( apply )) || { echo "dry run: nothing changed. Re-run with --apply."; exit 0; }
stamp=$(date +%Y%m%d-%H%M%S)
install -d /root/usb4-backup-m1n1-$stamp
cp -a "$cur" /root/usb4-backup-m1n1-$stamp/boot.bin
cp -a "$cur" /boot/m1n1/boot.bin.KNOWN-GOOD-pre-m1n1-$stamp
install -m755 "$tmp/new" /boot/m1n1/boot.bin.new
cmp "$tmp/new" /boot/m1n1/boot.bin.new && mv /boot/m1n1/boot.bin.new "$cur" && sync
echo "Installed. Backup: /boot/m1n1/boot.bin.KNOWN-GOOD-pre-m1n1-$stamp. Reboot, then check: ls /sys/bus/thunderbolt/devices; ip link; dmesg | grep -i acio"
