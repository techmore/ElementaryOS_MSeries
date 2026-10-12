#!/bin/bash
# Stage 2: update the m1n1 boot image with the USB4 kernel's device trees, and add a TEST GRUB entry.
# Needs stage 1 done first. Backups are in ~/fairydust-usb4/backup-*/ (restore boot.bin from there if needed).
set -euo pipefail
R=/mnt/fdbuild/root
KV=$(ls $R/usr/lib/modules | grep fairydust-usb4 | head -1)
[[ -n $KV ]] || { echo "stage 1 not done"; exit 1; }
[[ -f /boot/initramfs-linux-asahi-fairydust-usb4.img ]] || { echo "initramfs missing"; exit 1; }
chroot $R /bin/bash -c "DTBS='/usr/lib/modules/$KV/dtbs/*.dtb' update-m1n1"
ls -la /boot/m1n1
grep -q 'elementary-usb4-test' /boot/grub/custom.cfg || cat >> /boot/grub/custom.cfg <<'EOG'

# TEST entry: fairydust + USB4/Thunderbolt (not the default).
menuentry 'elementary OS (M-series, fairydust + USB4 TEST)' --id elementary-usb4-test {
    search --no-floppy --fs-uuid --set=root 9D41-85A1
    linux /vmlinuz-linux-asahi-fairydust-usb4 root=UUID=725346d2-f127-47bc-b464-9dd46155e8d6 rw cryptdevice=UUID=eec73af3-9f69-43bc-a114-c1197ac09c62:root:allow-discards loglevel=3 quiet splash rootflags=subvol=@elementary rw
    initrd /initramfs-linux-asahi-fairydust-usb4.img
}
EOG
echo STAGE2_DONE
