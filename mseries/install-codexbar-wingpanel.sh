#!/bin/bash
# Build and install the Pantheon-native CodexBar Wingpanel indicator.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
src="$repo/mseries/codexbar-wingpanel"

if [[ ${1:-} == --uninstall ]]; then
  indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
  sudo rm -f "$indicators_dir/libcodexbar.so"
  source "$repo/mseries/lib-codexbar.sh"
  for mark in "${CODEXBAR_MARKS[@]}"; do
    sudo rm -f "/usr/share/icons/hicolor/scalable/apps/mseries-codexbar-$mark-symbolic.svg"
  done
  rm -f "$HOME/.local/bin/codexbar-settings"
  if command -v gtk-update-icon-cache >/dev/null; then
    sudo gtk-update-icon-cache -f /usr/share/icons/hicolor
  fi
  echo 'Removed the CodexBar Wingpanel indicator. Log out and back in to reload Wingpanel.'
  exit 0
fi

mseries_apt_refresh
sudo apt-get install -y meson ninja-build valac pkg-config \
  libwingpanel-9-dev libgranite-7-dev libjson-glib-dev \
  python3-gi gir1.2-granite-7.0 gir1.2-webkit-6.0

source "$repo/mseries/lib-codexbar.sh"
# The panel runs these helpers directly (e.g. Claude switching imports the history and handoff modules).
codexbar_install_helpers "$repo"

for tool in meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo '  sudo apt install meson ninja-build valac libwingpanel-9-dev libgranite-7-dev libjson-glib-dev' >&2
    exit 1
  }
done

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/codexbar-wingpanel.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
meson setup "$build_dir" "$src" --prefix=/usr
ninja -C "$build_dir"
meson test -C "$build_dir" --print-errorlogs
sudo ninja -C "$build_dir" install
sudo rm -f /usr/share/icons/hicolor/scalable/apps/mseries-codexbar-openai.svg
if command -v gtk-update-icon-cache >/dev/null; then
  sudo gtk-update-icon-cache -f /usr/share/icons/hicolor
fi
echo 'Installed CodexBar in Wingpanel. The dropdown shows compact quota rows with reset times, pace tooltips, and account actions.'
