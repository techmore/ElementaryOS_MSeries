#!/bin/bash
# Install the freshly built m1n1 (USB4 tunable/DROM support) into boot.bin, and pin update-m1n1
# to the USB4 kernel's device trees so a later package hook cannot revert them.
#
# THIS REPLACES THE BOOTLOADER STAGE THAT RUNS BEFORE GRUB. Read RECOVERY.md first.
# Run as root after build-m1n1.sh:   sudo ./install-m1n1.sh
set -euo pipefail
R=/mnt/fdbuild/root
KV=${KV:-7.1.13-1-2-fairydust-usb4-ARCH}
NEW=$R/home/techmore/m1n1-build/m1n1/build/m1n1.bin
DEST=/usr/local/lib/asahi-boot/m1n1-usb4.bin

[[ -f $NEW ]] || { echo "no $NEW - run build-m1n1.sh first" >&2; exit 1; }
for f in boot.bin.KNOWN-GOOD-usb4-test RECOVERY.txt; do
  [[ -f /boot/m1n1/$f ]] || { echo "refusing: /boot/m1n1/$f missing (recovery copy not in place)" >&2; exit 1; }
done
cmp -s /boot/m1n1/boot.bin /boot/m1n1/boot.bin.KNOWN-GOOD-usb4-test \
  || echo "note: current boot.bin differs from KNOWN-GOOD-usb4-test (fine if intentional)"

mountpoint -q $R/boot || mount --bind /boot $R/boot
install -D -m 0644 "$NEW" "$R$DEST"
cat > $R/etc/default/update-m1n1 <<EOF
# Managed by ElementaryOS_MSeries mseries/fairydust/usb4/install-m1n1.sh
# Newer m1n1 with ACIO/USB4 tunables (distro m1n1 1.6.1 lacks them) ...
M1N1=$DEST
# ... and the USB4 kernel's DTBs, so pacman's 95-m1n1-install.hook cannot swap in stock ones.
DTBS="/usr/lib/modules/$KV/dtbs/*.dtb"
EOF
chroot $R /usr/sbin/update-m1n1

BIN=/boot/m1n1/boot.bin
echo "--- verify"
ls -la /boot/m1n1
want=$(stat -c%s "$NEW")
if cmp -s -n "$want" "$BIN" "$NEW"; then echo "OK: boot.bin starts with the new m1n1 ($want bytes)"; else echo "FAIL: boot.bin does not start with new m1n1" >&2; exit 1; fi
echo "usb4 DT markers: $(grep -ac 'usb4-0-acio' "$BIN")  (must be > 0)"
echo "tunable-rc strings in m1n1 part: $(head -c "$want" "$BIN" | grep -ac 'apple,tunable-rc')  (must be > 0)"
echo INSTALL_M1N1_DONE
