#!/usr/bin/env bash
# Install the M-series updater from this checkout (the supported route for customers is the
# mseries-update .deb from the signed repository; this is for development machines).
#
#   sudo bash mseries/update/install.sh              # install the command and the systemd units
#   sudo bash mseries/update/install.sh --uninstall  # remove them (state and logs are kept)
#   DESTDIR=/tmp/root bash mseries/update/install.sh # stage into a directory (used by the tests)
#
# Nothing is enabled or started and no update source is configured: run
# `sudo mseries-update init ...` and `sudo systemctl enable mseries-update-boot.service
# mseries-update-confirm.service` yourself. Wingpanel, the dock and the compositor are never touched.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
dest=${DESTDIR:-}
units=(mseries-update-boot.service mseries-update-confirm.service mseries-update-auto.service mseries-update-auto.timer)

if [[ ${1:-} == --uninstall ]]; then
  rm -f "$dest/usr/sbin/mseries-update"
  for unit in "${units[@]}"; do rm -f "$dest/usr/lib/systemd/system/$unit"; done
  [[ -n $dest ]] || systemctl daemon-reload
  echo "Removed. Update state (/var/lib/mseries-update) and the log were kept."
  exit 0
fi

install -Dm0755 "$here/mseries-update.py" "$dest/usr/sbin/mseries-update"
for unit in "${units[@]}"; do install -Dm0644 "$here/systemd/$unit" "$dest/usr/lib/systemd/system/$unit"; done
[[ -n $dest ]] || systemctl daemon-reload
echo "Installed mseries-update. Nothing is enabled; see mseries/UPDATER-DESIGN.md."
