#!/usr/bin/env bash
# Install Work Mode in elementary OS System Settings and schedule its wallpaper.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/work-mode"
bin="$HOME/.local/bin/mseries-work-mode"
launch_dock="$HOME/.local/bin/mseries-work-mode-dock"
unit_dir="$HOME/.config/systemd/user"
schema=io.elementary.mseries.work-mode.gschema.xml
plugsdir=$(pkg-config --variable=plugsdir switchboard-3)
plug="$plugsdir/personal/libmseries-work-mode.so"
schema_dir="$(pkg-config --variable=datadir glib-2.0)/glib-2.0/schemas"

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-work-mode.timer 2>/dev/null || true
  systemctl --user disable mseries-work-mode.service 2>/dev/null || true
  if [[ -x $bin ]]; then "$bin" --restore || true; fi
  systemctl --user stop mseries-work-mode-dock.service 2>/dev/null || true
  rm -f "$bin" "$launch_dock" "$unit_dir/mseries-work-mode.service" "$unit_dir/mseries-work-mode.timer" "$unit_dir/mseries-work-mode-dock.service"
  background_dir="$(pkg-config --variable=datadir glib-2.0)/backgrounds/mseries"
  sudo rm -f "$plug" "$schema_dir/$schema" "$background_dir/work-mode-azure-bloom.png" "$background_dir/work-mode-blue-flow.png" "$background_dir/work-mode-blue-ribbons.png" "$background_dir/work-mode-violet-arc.png" "$background_dir/work-mode-forest-flow.png"
  sudo rmdir "$(pkg-config --variable=datadir glib-2.0)/backgrounds/mseries" 2>/dev/null || true
  sudo glib-compile-schemas "$schema_dir"
  systemctl --user daemon-reload
  echo 'Removed Work Mode from System Settings. Your saved wallpaper and schedule settings were retained.'
  exit 0
fi

for command in python3 meson ninja valac pkg-config; do
  command -v "$command" >/dev/null || { echo "Missing build/runtime dependency: $command" >&2; exit 1; }
done
python3 -c 'import gi; gi.require_version("Gio", "2.0")' 2>/dev/null || {
  echo 'Missing Python Gio bindings (python3-gi).' >&2; exit 1;
}
pkg-config --exists switchboard-3 gtk4 libadwaita-1 granite-7 gee-0.8 || {
  echo 'Missing elementary Switchboard build dependencies:' >&2
  echo '  sudo apt install valac meson ninja-build libswitchboard-3-dev libgranite-7-dev libgtk-4-dev libadwaita-1-dev libgee-0.8-dev' >&2
  exit 1
}

install -Dm0755 "$src/mseries-work-mode" "$bin"
install -Dm0755 "$src/mseries-work-mode-dock" "$launch_dock"
install -Dm0755 "$src/mseries-desktop-mode" "$HOME/.local/bin/mseries-desktop-mode"
install -Dm0644 "$src/io.github.techmore.DesktopMode.desktop" "$HOME/.local/share/applications/io.github.techmore.DesktopMode.desktop"
install -Dm0644 "$src/mseries-work-mode.service" "$HOME/.config/systemd/user/mseries-work-mode.service"
install -Dm0644 "$src/mseries-work-mode.timer" "$HOME/.config/systemd/user/mseries-work-mode.timer"
install -Dm0644 "$src/mseries-work-mode-dock.service" "$HOME/.config/systemd/user/mseries-work-mode-dock.service"
build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
meson setup "$build" "$src" --prefix=/usr
ninja -C "$build"
sudo ninja -C "$build" install
sudo glib-compile-schemas "$schema_dir"
systemctl --user daemon-reload
systemctl --user enable --now mseries-work-mode.timer
systemctl --user enable mseries-work-mode.service

echo 'Installed Windows Work Mode in System Settings → Personal → Windows Work Mode.'
echo 'Choose a work wallpaper, turn Windows Work Mode on, and optionally set work hours.'
echo 'Revert: bash mseries/install-work-mode.sh --uninstall'
