#!/usr/bin/env bash
# Put the Apple display crossbar module into the fairydust initramfs images.
#
# Why: apple-dcp defers its probe until mux-apple-display-crossbar ("dp-xbar") exists. Without it in
# the initramfs the kernel logs "Failed to get dp-xbar: -517" ~70x per boot and the display comes up
# ~2.6 s late, which also widens the race between the greeter and the display driver.
#
# Why the existing drop-in (mseries/boot/zz_mseries_boot.conf) did not work: mkinitcpio only reads
# /etc/mkinitcpio.conf.d/*.conf when NO config is given with -c or via a preset's ALL_config. The
# fairydust presets set ALL_config, so every drop-in is silently ignored for them. This script puts the
# (conditional) snippet into /etc/mkinitcpio.conf itself, which is always read. The stock linux-asahi
# preset leaves ALL_config commented out, so it keeps using the drop-in.
#
# Safety: backs up /etc/mkinitcpio.conf and both images (on the ESP), rebuilds only the two fairydust
# presets, verifies the new images still contain btrfs + dm-crypt + the crossbar, and restores the
# backups if not. Run as root:  sudo bash mseries/install-initramfs-crossbar.sh
set -euo pipefail

R=/mnt/fdbuild/root
conf=$R/etc/mkinitcpio.conf
marker='ElementaryOS_MSeries: display crossbar'
presets=(linux-asahi-fairydust linux-asahi-fairydust-usb4)

mkdir -p "$R"
mountpoint -q "$R"      || mount -o subvol=@ /dev/mapper/root "$R"
for m in dev proc sys; do mountpoint -q "$R/$m" || mount --bind "/$m" "$R/$m"; done
mountpoint -q "$R/run"  || mount -t tmpfs -o mode=755 tmpfs "$R/run"
mountpoint -q "$R/boot" || mount --bind /boot "$R/boot"

stamp=$(date +%Y%m%d-%H%M%S)
[[ -f $conf.mseries-backup ]] || cp -a "$conf" "$conf.mseries-backup"
for p in "${presets[@]}"; do
  img=/boot/initramfs-$p.img
  [[ -f $img ]] || { echo "missing $img" >&2; exit 1; }
  cp -a "$img" "$img.bak-$stamp"
done
echo "backups: /boot/initramfs-*.img.bak-$stamp and $conf.mseries-backup"

if ! grep -q "$marker" "$conf"; then
  cat >> "$conf" <<'EOF'

# ElementaryOS_MSeries: display crossbar. apple-dcp defers until mux-apple-display-crossbar is
# available; add it only where the kernel builds it (mkinitcpio fails the image over a MODULES
# entry it cannot find).
if modinfo -k "${KERNELVERSION:-$(uname -r)}" mux_apple_display_crossbar >/dev/null 2>&1; then
  MODULES+=(mux_apple_display_crossbar)
fi
EOF
fi

restore() {
  echo "VERIFICATION FAILED - restoring backups" >&2
  cp -a "$conf.mseries-backup" "$conf"
  for p in "${presets[@]}"; do cp -a "/boot/initramfs-$p.img.bak-$stamp" "/boot/initramfs-$p.img"; done
}

for p in "${presets[@]}"; do
  chroot "$R" /bin/bash -c "mkinitcpio -p $p" >/dev/null 2>&1 || { echo "mkinitcpio -p $p failed" >&2; restore; exit 1; }
  listing=$(chroot "$R" lsinitcpio "/boot/initramfs-$p.img")
  for need in btrfs.ko dm-crypt.ko; do
    grep -q "$need" <<<"$listing" || { echo "$p: $need missing" >&2; restore; exit 1; }
  done
  if grep -q 'mux-apple-display-crossbar' <<<"$listing"; then
    echo "$p: crossbar included, size $(stat -c%s "/boot/initramfs-$p.img")"
  else
    echo "$p: crossbar NOT included (kernel may not build it) - image otherwise fine"
  fi
done
echo INITRAMFS_CROSSBAR_DONE
