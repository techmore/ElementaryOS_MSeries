#!/bin/bash
# Stage 1: install the linux-asahi-fairydust-usb4 package (beside the existing kernels) and build its initramfs.
# Does NOT touch the m1n1 boot image or the default GRUB entry. Run as root: sudo bash install-stage1.sh
set -euo pipefail
R=/mnt/fdbuild/root
mkdir -p $R
mountpoint -q $R      || mount -o subvol=@ /dev/mapper/root $R
for m in dev proc sys; do mountpoint -q $R/$m || mount --bind /$m $R/$m; done
mountpoint -q $R/run  || mount -t tmpfs -o mode=755 tmpfs $R/run
mountpoint -q $R/home || mount -o subvol=@home /dev/mapper/root $R/home
mountpoint -q $R/boot || mount --bind /boot $R/boot
PKG=/home/techmore/usb4-pkg/linux-asahi-fairydust-usb4-7.1.13.fairydust.usb4-1-aarch64.pkg.tar.xz
cat > $R/etc/mkinitcpio.d/linux-asahi-fairydust-usb4.preset <<'EOP'
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux-asahi-fairydust-usb4"
PRESETS=('default')
default_image="/boot/initramfs-linux-asahi-fairydust-usb4.img"
EOP
chroot $R /bin/bash -c "pacman -U --noconfirm $PKG"
KV=$(basename "$(compgen -G "$R/usr/lib/modules/*fairydust-usb4*" | head -1)")
echo "installed kernel: $KV"
install -Dm644 "$R/usr/lib/modules/$KV/vmlinuz" /boot/vmlinuz-linux-asahi-fairydust-usb4
chroot $R /bin/bash -c "mkinitcpio -p linux-asahi-fairydust-usb4"
ls -la /boot/*usb4*
echo STAGE1_DONE
