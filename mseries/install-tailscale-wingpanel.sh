#!/usr/bin/env bash
# Tailscale menu in the top panel: status, on/off, and your tailnet devices with
# one-click "Copy IP" / "Copy ssh command".
#
#   bash mseries/install-tailscale-wingpanel.sh              # build and install (asks for sudo)
#   bash mseries/install-tailscale-wingpanel.sh --uninstall
#
# Wingpanel watches its plugin folder, so the icon appears without a restart.
# The Work Mode taskbar gets the same menu through install-dock-drawers.sh.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9 2>/dev/null || echo /usr/lib/aarch64-linux-gnu/wingpanel-9)
icon=/usr/share/icons/hicolor/symbolic/apps/mseries-tailscale-symbolic.svg

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f "$indicators_dir/libmseries-tailscale.so" "$icon"
  echo 'Tailscale menu removed from the top panel.'
  exit 0
fi
[[ -z ${1:-} ]] || { echo 'Usage: install-tailscale-wingpanel.sh [--uninstall]' >&2; exit 2; }

for tool in meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo '  sudo apt install meson ninja-build valac libwingpanel-9-dev libgranite-7-dev libjson-glib-dev' >&2
    exit 1
  }
done

# Build on disk, not in RAM-backed /tmp.
build=${XDG_CACHE_HOME:-$HOME/.cache}/mseries-build/tailscale-wingpanel
rm -rf "$build"
meson setup "$build" "$repo/mseries/tailscale-wingpanel" --prefix=/usr >/dev/null
ninja -C "$build" >/dev/null

sudo install -Dm0644 "$repo/mseries/tailscale-wingpanel/mseries-tailscale-symbolic.svg" "$icon"
sudo gtk-update-icon-cache -q -t -f /usr/share/icons/hicolor 2>/dev/null || :
# Wingpanel loads any new file in its folder, so stage outside it and move in at once.
pending="$indicators_dir/../mseries-pending-indicators"
sudo install -Dm0755 "$build/libmseries-tailscale.so" "$pending/libmseries-tailscale.so"
sudo mv -f "$pending/libmseries-tailscale.so" "$indicators_dir/libmseries-tailscale.so"
rm -rf "$build"

if ! tailscale debug prefs 2>/dev/null | grep -q "\"OperatorUser\": \"$USER\""; then
  echo 'Tip: to turn Tailscale on/off from the menu without sudo, run once:'
  echo "  sudo tailscale set --operator=$USER"
fi
echo 'Installed. The Tailscale icon is in the top panel.'
