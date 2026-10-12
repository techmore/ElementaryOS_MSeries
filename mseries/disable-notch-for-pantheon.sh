#!/bin/bash
# Restore the rectangular display mode so centered Pantheon indicators avoid the camera notch.
set -euo pipefail

sudo install -D -m 0644 /dev/stdin /etc/modprobe.d/zz-pantheon-notch.conf <<'EOF'
# Pantheon Wingpanel does not yet avoid the M-series camera notch.
options appledrm show_notch=0
EOF

if command -v update-initramfs >/dev/null; then
  sudo update-initramfs -u -k all
elif command -v mkinitcpio >/dev/null; then
  sudo mkinitcpio -P
elif command -v dracut >/dev/null; then
  sudo dracut --regenerate-all --force
else
  echo 'No known initramfs generator found; modprobe config is installed. Rebuild the initramfs manually if your system embeds modprobe.d.' >&2
fi

echo 'Pantheon notch setting installed. Reboot to restore the cropped 16:10 desktop mode and reveal the centered clock.'
