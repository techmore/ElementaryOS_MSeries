#!/usr/bin/env bash
# Native arm64 RDP client for Horizon-hosted desktops, from Ubuntu's FreeRDP 3 packages (no proprietary client).
#   bash mseries/install-horizon-rdp.sh              # install FreeRDP + the horizon-rdp launcher
#   bash mseries/install-horizon-rdp.sh --uninstall  # remove the launcher and desktop entry (keeps FreeRDP)
# Omnissa's Horizon Client has no public arm64 Linux build. This reaches a desktop over plain RDP only, so the
# desktop's RDP must be enabled and reachable; see mseries/HORIZON-RDP.md for what that does and does not cover.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$here/lib-apt.sh"
bin=/usr/local/bin/horizon-rdp
entry=/usr/share/applications/horizon-rdp.desktop

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f "$bin" "$entry"
  echo 'Removed launcher (FreeRDP packages left installed).'
  exit 0
fi

if ! dpkg -s freerdp3-sdl freerdp3-x11 >/dev/null 2>&1; then
  mseries_apt_refresh
  sudo apt-get install -y freerdp3-sdl freerdp3-x11
fi
sudo install -m 0755 "$here/horizon-rdp" "$bin"
sudo install -m 0644 "$here/horizon-rdp.desktop" "$entry"
command -v update-desktop-database >/dev/null && sudo update-desktop-database /usr/share/applications || true
dpkg-query -W -f='FreeRDP ${Version}\n' freerdp3-sdl
echo 'Installed: run "horizon-rdp --help" or open "Horizon RDP" from the app launcher.'
