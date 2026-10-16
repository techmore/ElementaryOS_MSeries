#!/usr/bin/env bash
# Make Electron/Chromium apps use native Wayland instead of Xwayland. The ChatGPT desktop app runs as an X11
# client here and submits about 4,000 to 5,000 GPU jobs/s (see POWER-OPPORTUNITIES-2026-10-16.md).
# Takes effect at next login for newly started apps; running apps are not touched.
#   install-electron-wayland.sh              install
#   install-electron-wayland.sh --uninstall  remove
set -euo pipefail
conf=$HOME/.config/environment.d/60-mseries-electron-wayland.conf
if [[ ${1:-} == --uninstall ]]; then
  rm -f "$conf"
  echo 'Removed. Log out and in to apply.'
  exit 0
fi
mkdir -p "$(dirname "$conf")"
printf '# ElementaryOS_MSeries: native Wayland for Electron apps (fewer GPU jobs than Xwayland, to be measured).\nELECTRON_OZONE_PLATFORM_HINT=auto\n' > "$conf"
echo "Wrote $conf. Log out and in to apply."
