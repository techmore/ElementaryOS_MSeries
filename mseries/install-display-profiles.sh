#!/usr/bin/env bash
# Install the display profile saver/watcher for the current user.
#   bash mseries/install-display-profiles.sh              # install and start the watcher
#   bash mseries/install-display-profiles.sh --uninstall  # remove
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
here=$root/display-profiles app=$root/display-settings
bin=$HOME/.local/bin auto=$HOME/.config/autostart apps=$HOME/.local/share/applications
if [[ ${1:-} == --uninstall ]]; then
  pkill -f "$bin/mseries-display-profiles watch" 2>/dev/null || true
  rm -f "$bin/mseries-display-profiles" "$auto/mseries-display-profiles.desktop" "$bin/mseries-display-settings" "$bin/display_diag.py" "$apps/mseries-display-settings.desktop"
  echo "Removed display profiles (saved profiles in ~/.config/mseries are kept)."; exit 0
fi
command -v python3 >/dev/null && python3 -c "import gi.repository.Gtk" 2>/dev/null || true
dpkg -s python3-gi-cairo >/dev/null 2>&1 || sudo apt-get install -y python3-gi-cairo
mkdir -p "$bin" "$auto" "$apps"
install -m 755 "$here/mseries-display-profiles" "$bin/mseries-display-profiles"
install -m 644 "$here/mseries-display-profiles.desktop" "$auto/mseries-display-profiles.desktop"
install -m 755 "$app/mseries-display-settings" "$bin/mseries-display-settings"
install -m 644 "$app/display_diag.py" "$bin/display_diag.py"
install -m 644 "$app/mseries-display-settings.desktop" "$apps/mseries-display-settings.desktop"
update-desktop-database "$apps" 2>/dev/null || true
pkill -f "$bin/mseries-display-profiles watch" 2>/dev/null || true
mkdir -p "$HOME/.cache"
setsid nohup "$bin/mseries-display-profiles" watch >>"$HOME/.cache/mseries-display-profiles.log" 2>&1 &
echo "Display profiles watcher running. Save a layout with: mseries-display-profiles save NAME"
