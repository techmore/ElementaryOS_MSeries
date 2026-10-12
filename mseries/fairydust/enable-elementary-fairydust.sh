#!/bin/bash
# enable-elementary-fairydust.sh — make the already-built fairydust kernel
# bootable with the *elementary* root (not just the Arch/omarchy one).
#
# Run from elementary as root:   sudo mseries/fairydust/enable-elementary-fairydust.sh
#
# What it does:
#   1. Copies the fairydust module tree out of the Arch (@) subvolume into the
#      elementary root, so modules resolve after switch_root (the initramfs is
#      built on the Arch side and is shared, but modules are not).
#   2. Writes a GRUB menuentry to /boot/grub/custom.cfg, which the generated
#      /boot/grub/grub.cfg sources via 41_custom — no grub-mkconfig re-run and
#      the stock elementary entry is left untouched as a rescue path.
#
# Assumes the fairydust package was already installed on the Arch side (see
# host/fairydust-build.sh) so /boot/vmlinuz-linux-asahi-fairydust and
# /boot/initramfs-linux-asahi-fairydust.img exist.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run me as root (sudo)." >&2; exit 1; }

# elementary root identity (matches 40_elementary-grow in grub.cfg).
ESP_UUID=${ESP_UUID:-9D41-85A1}
ROOT_UUID=${ROOT_UUID:-725346d2-f127-47bc-b464-9dd46155e8d6}
CRYPT_UUID=${CRYPT_UUID:-eec73af3-9f69-43bc-a114-c1197ac09c62}
SUBVOL=${SUBVOL:-@elementary}

[[ -f /boot/vmlinuz-linux-asahi-fairydust ]] \
  || { echo "missing /boot/vmlinuz-linux-asahi-fairydust — build the kernel first." >&2; exit 1; }
[[ -f /boot/initramfs-linux-asahi-fairydust.img ]] \
  || { echo "missing /boot/initramfs-linux-asahi-fairydust.img." >&2; exit 1; }

# 1. modules
tmp=$(mktemp -d)
trap 'umount "$tmp" 2>/dev/null || true; rmdir "$tmp" 2>/dev/null || true' EXIT
mount -o subvolid=5 /dev/mapper/root "$tmp"
krel=$(ls "$tmp"/@/usr/lib/modules | grep fairydust | sort -V | tail -n1 || true)
[[ -n $krel ]] || { echo "no fairydust module tree on the Arch (@) subvol." >&2; exit 1; }
if [[ -d /usr/lib/modules/$krel ]]; then
  echo "modules already present: /usr/lib/modules/$krel"
else
  echo "copying /usr/lib/modules/$krel into the elementary root"
  cp -a --reflink=auto "$tmp/@/usr/lib/modules/$krel" /usr/lib/modules/
fi
umount "$tmp" 2>/dev/null || true

# 2. GRUB entry
cat > /boot/grub/custom.cfg <<EOF
menuentry 'elementary OS (M-series, fairydust DP-altmode)' {
    search --no-floppy --fs-uuid --set=root $ESP_UUID
    linux /vmlinuz-linux-asahi-fairydust root=UUID=$ROOT_UUID rw cryptdevice=UUID=$CRYPT_UUID:root:allow-discards loglevel=3 quiet splash rootflags=subvol=$SUBVOL rw
    initrd /initramfs-linux-asahi-fairydust.img
}
EOF
echo "wrote /boot/grub/custom.cfg:"
cat /boot/grub/custom.cfg
echo
echo "Done. Reboot, pick 'elementary OS (M-series, fairydust DP-altmode)' in GRUB,"
echo "plug the dock into the FRONT-LEFT USB-C port, then run verify.sh."
