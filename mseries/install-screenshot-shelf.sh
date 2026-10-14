#!/usr/bin/env bash
# Install the screenshot thumbnail shelf and the Markup launcher for the current user.
#   bash mseries/install-screenshot-shelf.sh              # install and start
#   bash mseries/install-screenshot-shelf.sh --uninstall  # remove
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/screenshot-shelf" && pwd)
bin=$HOME/.local/bin libexec=$HOME/.local/libexec apps=$HOME/.local/share/applications auto=$HOME/.config/autostart
if [[ ${1:-} == --uninstall ]]; then
  pkill -f "$libexec/mseries-screenshot-shelf" 2>/dev/null || true
  rm -f "$libexec/mseries-screenshot-shelf" "$bin/mseries-markup" "$apps/mseries-markup.desktop" "$auto/mseries-screenshot-shelf.desktop"
  echo "Removed the shelf and Markup."; exit 0
fi
command -v swappy >/dev/null || sudo apt-get install -y swappy
mkdir -p "$bin" "$libexec" "$apps" "$auto"
install -m 755 "$here/mseries-screenshot-shelf" "$libexec/mseries-screenshot-shelf"
install -m 755 "$here/mseries-markup" "$bin/mseries-markup"
install -m 644 "$here/mseries-markup.desktop" "$apps/mseries-markup.desktop"
install -m 644 "$here/mseries-screenshot-shelf.desktop" "$auto/mseries-screenshot-shelf.desktop"
update-desktop-database "$apps" 2>/dev/null || true
pkill -f "$libexec/mseries-screenshot-shelf" 2>/dev/null || true
setsid nohup "$libexec/mseries-screenshot-shelf" >/dev/null 2>&1 &
echo "Screenshot shelf running. Log: ~/.cache/mseries-screenshot-shelf.log"
