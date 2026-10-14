#!/bin/bash
# Restore the rectangular display mode so centered Pantheon indicators avoid the camera notch.
# LEGACY HOTFIX: this edits the generated /boot/grub/grub.cfg in place, which the next
# grub-mkconfig discards. transform/elementary-grow.sh now writes appledrm.show_notch=0 into the
# entry it generates (run `elementary-grow.sh --repair-grub`) and the layer ships the modprobe
# option, so a grown root does not need this script.
set -euo pipefail

sudo install -D -m 0644 /dev/stdin /etc/modprobe.d/zz-pantheon-notch.conf <<'EOF'
# Pantheon Wingpanel does not yet avoid the M-series camera notch.
options appledrm show_notch=0
EOF

grub_cfg=/boot/grub/grub.cfg
[[ -f $grub_cfg ]] || { echo "Missing $grub_cfg; refusing to guess the active boot configuration." >&2; exit 1; }
if [[ ! -e "$grub_cfg.pre-pantheon-notch" ]]; then
  sudo cp -a "$grub_cfg" "$grub_cfg.pre-pantheon-notch"
fi
# The installed elementary entry is custom and uses the @elementary subvolume.
# Pass the module option on the kernel command line so it applies even when
# appledrm loads from the Asahi initramfs before the root filesystem is mounted.
sudo sed -i '/^[[:space:]]*linux .*rootflags=subvol=@elementary/ {
  /appledrm\.show_notch=0/! s/$/ appledrm.show_notch=0/
}' "$grub_cfg"
if ! grep -q '^[[:space:]]*linux .*rootflags=subvol=@elementary.*appledrm\.show_notch=0' "$grub_cfg"; then
  echo 'Could not find the elementary @elementary GRUB kernel line; no boot entry was changed.' >&2
  exit 1
fi

echo 'Pantheon notch setting added to the elementary GRUB entry. Reboot to restore the cropped 16:10 desktop mode and reveal the centered clock.'
