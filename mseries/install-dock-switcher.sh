#!/usr/bin/env bash
# Dock & Taskbar in System Settings (M-series).
#
#   bash mseries/install-dock-switcher.sh              # build and install the page
#   bash mseries/install-dock-switcher.sh --uninstall  # remove it
#
# Adds Settings -> Personal -> Dock & Taskbar: switch between the Windows 11
# taskbar and the elementary dock, and choose when the dock hides. It is a
# Switchboard plug (GTK 4 + libadwaita), built like Work Mode and Touch ID.
#
# Installs only the plug into Switchboard's personal/ directory. It never
# restarts Settings, the dock, Wingpanel or the compositor: the page loads the
# next time System Settings is opened, and the dock already follows its
# `taskbar-mode` setting live.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/dock-switcher"
plugsdir=$(pkg-config --variable=plugsdir switchboard-3 2>/dev/null || true)
plug="$plugsdir/personal/libmseries-dock-taskbar.so"

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f "$plug"
  echo 'Removed Dock & Taskbar from System Settings. Dock settings were left as they are.'
  exit 0
fi

for command in meson ninja valac pkg-config; do
  command -v "$command" >/dev/null || { echo "Missing build dependency: $command" >&2; exit 1; }
done
pkg-config --exists switchboard-3 gtk4 'libadwaita-1 >= 1.6' gee-0.8 || {
  echo 'Missing elementary Switchboard build dependencies:' >&2
  echo '  sudo apt install valac meson ninja-build libswitchboard-3-dev libgtk-4-dev libadwaita-1-dev libgee-0.8-dev' >&2
  exit 1
}

build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
meson setup "$build" "$src" --prefix=/usr
ninja -C "$build"
meson test -C "$build" --print-errorlogs
sudo ninja -C "$build" install

echo 'Installed. Open System Settings -> Personal -> Dock & Taskbar.'
echo 'Remove with: bash mseries/install-dock-switcher.sh --uninstall'
