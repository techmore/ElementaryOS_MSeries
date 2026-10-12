#!/bin/bash
# Deploy the rebuilt device trees (with the USB4 graph endpoints) and refresh the m1n1 boot image.
# Backs up /boot/m1n1 first. No files are deleted. Run as root: sudo bash deploy-dtbs.sh
set -euo pipefail
KV=7.1.13-1-2-fairydust-usb4-ARCH
R=/mnt/fdbuild/root
S=$R/home/techmore/usb4-pkg/src/linux-fairydust/build/base/arch/arm64/boot/dts/apple
B2=${USB4_WORKDIR:-$HOME/fairydust-usb4}/backup-pre-dtfix-$(date +%H%M%S)

mkdir -p "$B2"
cp -a /boot/m1n1 "$B2/"
chown -R admin:admin "$B2"
echo "backup: $B2"

cp "$S"/*.dtb "$R/usr/lib/modules/$KV/dtbs/"
cp "$S"/*.dtb "/usr/lib/modules/$KV/dtbs/"
echo "dtbs updated in both roots"

mountpoint -q "$R/boot" || mount --bind /boot "$R/boot"
chroot "$R" /bin/bash -c "DTBS='/usr/lib/modules/$KV/dtbs/*.dtb' update-m1n1"

ls -la /boot/m1n1
echo "usb4 strings in new boot.bin: $(grep -ac 'usb4-0-acio' /boot/m1n1/boot.bin)"
echo "usb4 strings in backup:       $(grep -ac 'usb4-0-acio' "$B2/m1n1/boot.bin")"
echo DEPLOY_DONE
