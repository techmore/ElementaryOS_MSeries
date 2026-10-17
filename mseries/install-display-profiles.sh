#!/usr/bin/env bash
# Install the display profile saver/watcher for the current user.
#   bash mseries/install-display-profiles.sh              # install and start the watcher
#   bash mseries/install-display-profiles.sh --uninstall  # remove
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/display-profiles" && pwd)
bin=$HOME/.local/bin auto=$HOME/.config/autostart
if [[ ${1:-} == --uninstall ]]; then
  pkill -f "$bin/mseries-display-profiles watch" 2>/dev/null || true
  rm -f "$bin/mseries-display-profiles" "$auto/mseries-display-profiles.desktop"
  echo "Removed display profiles (saved profiles in ~/.config/mseries are kept)."; exit 0
fi
mkdir -p "$bin" "$auto"
install -m 755 "$here/mseries-display-profiles" "$bin/mseries-display-profiles"
install -m 644 "$here/mseries-display-profiles.desktop" "$auto/mseries-display-profiles.desktop"
pkill -f "$bin/mseries-display-profiles watch" 2>/dev/null || true
setsid nohup "$bin/mseries-display-profiles" watch >/dev/null 2>&1 &
echo "Display profiles watcher running. Save a layout with: mseries-display-profiles save NAME"
