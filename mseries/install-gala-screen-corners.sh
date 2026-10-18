#!/usr/bin/env bash
# Rounded corners on the built-in display (like macOS), via a patched Gala:
#  * rounded masks over the four screen corners (GALA_SCREEN_CORNER_RADIUS),
#  * rounded corners on every standard window (GALA_WINDOW_CORNER_RADIUS), and
#  * a software dim layer below the panel's 2-nit backlight floor (mseries-brightness keys
#    use it; patches/gala-screen-dim.patch).
#
#   bash mseries/install-gala-screen-corners.sh [--radius N] [--window-radius N]
#   bash mseries/install-gala-screen-corners.sh --disable      # go back to the stock Gala for your session
#
# SAFETY DESIGN
#  * The patched Gala lives in its own prefix (/usr/local/lib/mseries/gala). /usr/bin/gala and
#    its libraries are not touched.
#  * Only YOUR user session is pointed at it (a systemd user drop-in in ~/.config). The login
#    screen (greeter) keeps running the stock Gala, so you can always reach it.
#  * The launcher falls back to stock Gala on its own if the patched one dies within seconds of
#    starting, and stays on stock until you delete ~/.cache/mseries-gala-failed.
#  * Takes effect at the next login (the compositor cannot be swapped inside a running session).
#
# Radii are in logical pixels. Screen corners default to 20 (0 hides the masks); window
# corners default to 12 (0 leaves windows square). Change them later by editing
# GALA_SCREEN_CORNER_RADIUS / GALA_WINDOW_CORNER_RADIUS in the drop-in below and logging out/in.
#
# It also applies gala-panel-offset.patch, which lets a panel (the dock) ask the compositor to
# slide along its edge (io_elementary_pantheon_panel_v1.set_offset, protocol v2). The Dock's
# Command-drag uses it; without this Gala the dock simply stays centred.
# gala-dock-workarea.patch reserves visible dock space and releases it after hiding.

#
# And gala-screenshot-window-pick.patch: in the Command+Shift+4 selector a plain click on a window
# screenshots that window (macOS style); dragging still selects an area.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
prefix=/usr/local/lib/mseries/gala
commit=f0791434ac40a50f2aec64700a47b3bb04145752   # elementary/gala matching gala 8.6.2+r3174
dropin_dir=$HOME/.config/systemd/user/io.elementary.gala@wayland.service.d
dropin=$dropin_dir/mseries-screen-corners.conf
radius=20
window_radius=12

while [[ $# -gt 0 ]]; do
  case $1 in
    --disable)
      rm -f "$dropin"
      systemctl --user daemon-reload
      echo 'Disabled for your session (stock Gala at next login). The private build stays in '"$prefix"'.'
      exit 0 ;;
    --radius) radius=$2; shift 2 ;;
    --window-radius) window_radius=$2; shift 2 ;;
    *) echo "Unknown option $1" >&2; exit 1 ;;
  esac
done

for tool in git meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || { echo "Missing $tool (see build requirements below)." >&2; missing=1; }
done
for mod in libmutter-18 gnome-bg-4 ibus-1.0 granite-7 gtk4 gala; do
  pkg-config --exists "$mod" 2>/dev/null || { echo "Missing development files for $mod" >&2; missing=1; }
done
if [[ ${missing:-0} == 1 ]]; then
  echo 'Install build requirements with:' >&2
  echo '  sudo apt install git meson ninja-build valac libmutter-18-dev libgala-dev libgranite-7-dev libgtk-4-dev libibus-1.0-dev libgnome-bg-4-dev libgnome-desktop-4-dev libgee-0.8-dev' >&2
  exit 1
fi

installed_version=$(dpkg-query -W -f='${Version}' gala 2>/dev/null || true)
if [[ $installed_version != 8.6.2* ]]; then
  echo "This patch targets gala 8.6.2.x; found ${installed_version:-none}." >&2
  exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/gala-screen-corners.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT
source_dir="$work_dir/source"
build_dir="$work_dir/build"

git init -q "$source_dir"
git -C "$source_dir" remote add origin https://github.com/elementary/gala.git
git -C "$source_dir" fetch -q --depth=1 origin "$commit"
git -C "$source_dir" checkout -q --detach FETCH_HEAD
git -C "$source_dir" apply "$repo/mseries/patches/gala-screen-corners.patch"
git -C "$source_dir" apply "$repo/mseries/patches/gala-screen-dim.patch"
git -C "$source_dir" apply "$repo/mseries/patches/gala-window-corners.patch"
git -C "$source_dir" apply "$repo/mseries/patches/gala-panel-offset.patch"
git -C "$source_dir" apply "$repo/mseries/patches/gala-dock-workarea.patch"

git -C "$source_dir" apply "$repo/mseries/patches/gala-screenshot-window-pick.patch"

meson setup "$build_dir" "$source_dir" --prefix="$prefix" --libdir=lib --buildtype=release >/dev/null
ninja -C "$build_dir" >/dev/null
test -x "$build_dir/src/gala"
sudo meson install -C "$build_dir" --no-rebuild >/dev/null

# Launcher with automatic fallback to the stock compositor.
launcher=$prefix/bin/mseries-gala
sudo tee "$launcher" >/dev/null <<'LAUNCHER'
#!/bin/sh
# Start the patched Gala; fall back to the stock one if it cannot start.
flag="$HOME/.cache/mseries-gala-failed"
patched=/usr/local/lib/mseries/gala/bin/gala
libs=/usr/local/lib/mseries/gala/lib

use_stock() {
  logger -t mseries-gala "$1; starting stock /usr/bin/gala"
  exec /usr/bin/gala
}

[ -e "$flag" ] && use_stock "patched Gala disabled by $flag"
[ -x "$patched" ] || use_stock "patched Gala missing"
LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" ldd "$patched" 2>/dev/null | grep -q 'not found' && use_stock "patched Gala has unresolved libraries"

start=$(date +%s)
LD_LIBRARY_PATH="$libs${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$patched"
rc=$?
if [ "$rc" -ne 0 ] && [ $(( $(date +%s) - start )) -lt 15 ]; then
  mkdir -p "$(dirname "$flag")" && : > "$flag"
  logger -t mseries-gala "patched Gala failed after under 15 s (rc=$rc); disabled until $flag is removed"
fi
exit "$rc"
LAUNCHER
sudo chmod 0755 "$launcher"

mkdir -p "$dropin_dir"
cat > "$dropin" <<EOF
# ElementaryOS_MSeries: run the patched Gala (rounded screen corners and windows) for this user's session only.
# Delete this file (or run install-gala-screen-corners.sh --disable) and log out/in to revert.
[Service]
NotifyAccess=all
Environment=GALA_SCREEN_CORNER_RADIUS=$radius
Environment=GALA_WINDOW_CORNER_RADIUS=$window_radius
ExecStart=
ExecStart=$launcher
EOF
systemctl --user daemon-reload
systemd-analyze --user verify io.elementary.gala@wayland.service 2>&1 | grep -v '^$' | head -3 || true

echo "Installed. Log out and back in to see the rounded corners (screen ${radius}px, windows ${window_radius}px) and enable dynamic dock space plus the brightness keys' sub-2-nit steps."
echo "Revert: bash mseries/install-gala-screen-corners.sh --disable   (or delete $dropin)"
