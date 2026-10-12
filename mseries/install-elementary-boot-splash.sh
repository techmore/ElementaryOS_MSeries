#!/bin/bash
# Use the elementary Plymouth theme for the disk-encryption passphrase screen
# and fix the 10 second apple-dcp deferred-probe wait, by rebuilding the
# initramfs on the Arch (Omarchy) side that both systems boot from.
#
# Run from the elementary side. Backs up the current initramfs images first;
# `--uninstall` restores the Omarchy theme and those images.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
R=${ARCH_ROOT:-/mnt/fdbuild/root}
theme_src=/usr/share/plymouth/themes/elementary
theme_dst=$R/usr/share/plymouth/themes/elementary
dropin=$R/etc/mkinitcpio.conf.d/zz_mseries_boot.conf
plymouthd=$R/etc/plymouth/plymouthd.conf
stamp=pre-mseries

[[ -d $R/etc/mkinitcpio.conf.d ]] || { echo "Arch root not found at $R (set ARCH_ROOT)." >&2; exit 1; }

mounts=()
cleanup() {
  for ((i = ${#mounts[@]} - 1; i >= 0; i--)); do sudo umount "${mounts[i]}" 2>/dev/null || true; done
}
trap cleanup EXIT
bind() { sudo mount --bind "$1" "$2"; mounts+=("$2"); }

rebuild() {
  bind /boot "$R/boot"
  bind /proc "$R/proc"
  bind /sys "$R/sys"
  bind /dev "$R/dev"
  sudo chroot "$R" mkinitcpio -P
}

if [[ ${1:-} == --uninstall ]]; then
  sudo sed -i 's/^Theme=.*/Theme=omarchy/' "$plymouthd"
  sudo rm -f "$dropin"
  for img in /boot/initramfs-linux-asahi.img /boot/initramfs-linux-asahi-fairydust.img; do
    [[ -f $img.$stamp ]] && sudo cp "$img.$stamp" "$img"
  done
  echo 'Restored the Omarchy theme and the previous initramfs images.'
  exit 0
fi

# FAT /boot is small: need room for one backup of each image plus a rebuild.
avail_mb=$(df -m --output=avail /boot | tail -1)
(( avail_mb > 80 )) || { echo "Only ${avail_mb}MB free on /boot; need about 80MB." >&2; exit 1; }

for img in /boot/initramfs-linux-asahi.img /boot/initramfs-linux-asahi-fairydust.img; do
  [[ -f $img ]] && { [[ -f $img.$stamp ]] || sudo cp "$img" "$img.$stamp"; }
done

sudo rm -rf "$theme_dst"
sudo cp -a "$theme_src" "$theme_dst"
# Inter is not installed on the Arch side; Noto is.
sudo sed -i 's/^Font=.*/Font=Noto Sans 12/; s/^TitleFont=.*/TitleFont=Noto Sans Bold 32/' "$theme_dst/elementary.plymouth"
sudo sed -i 's#^ImageDir=.*#ImageDir=/usr/share/plymouth/themes/elementary#' "$theme_dst/elementary.plymouth"

sudo install -Dm644 "$repo/mseries/boot/zz_mseries_boot.conf" "$dropin"
if grep -q '^Theme=' "$plymouthd" 2>/dev/null; then
  sudo sed -i 's/^Theme=.*/Theme=elementary/' "$plymouthd"
else
  printf '[Daemon]\nTheme=elementary\n' | sudo tee "$plymouthd" >/dev/null
fi

rebuild
echo 'Rebuilt the initramfs. Reboot to see the elementary passphrase screen.'
echo "If anything goes wrong, boot from a rescue USB and copy the *.$stamp images in /boot back over the originals, or run: $0 --uninstall"
