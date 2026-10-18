#!/usr/bin/env bash
# Drawer assignment on the dock: a chevron that opens drop slots you drag apps onto.
#
#   bash mseries/install-dock-drawers.sh            # build, install privately, enable for your session
#   bash mseries/install-dock-drawers.sh --revert   # go back to the stock dock
#
# This is a patch to the elementary dock (io.elementary.dock), the same way
# install-gala-screen-corners.sh patches Gala. It adds a chevron at the end of
# the dock; its popover shows drawer slots (five by default, an arrow reveals the
# other four) that accept a dragged dock app or a dropped .desktop file and write
# ~/.config/mseries/gala-drawers.ini (which the Gala "drawers" plugin reloads
# live). It needs the drawers plugin for the slots to actually pop windows.
#
# SAFETY DESIGN
#  * The patched dock is a private build, nothing in /usr is touched.
#  * gnome-session launches the dock by name (PATH), and ~/.local/bin precedes
#    /usr/bin in this session, so a per-user wrapper there points the session at
#    the private build. The greeter and other sessions keep the stock dock.
#  * The wrapper falls back to /usr/bin/io.elementary.dock if the private build is
#    missing, has unresolved libraries, or dies within a few seconds; it then
#    stays on stock until ~/.cache/mseries-dock-failed is removed.
#  * Takes effect at the next login (the dock is already running).
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
commit=8b45a68a122947ad3a6427bf6e159ec2acf04ad0 # elementary/dock 8.3.3
prefix=${HOME}/.local/lib/mseries/dock
wrapper=${HOME}/.local/bin/io.elementary.dock
patched=$prefix/bin/io.elementary.dock
stock=/usr/bin/io.elementary.dock
patch=$repo/mseries/patches/dock-drawers.patch
startup_patch=$repo/mseries/patches/dock-workspace-startup.patch

mode=${1:-install}
case $mode in install|--build-only|--revert) ;; *) echo "Usage: $0 [--build-only|--revert]" >&2; exit 2;; esac
if [[ $mode == --revert ]]; then
  rm -f "$wrapper"
  echo "Reverted: the stock dock ($stock) is used at your next login."
  echo "The private build is left in $prefix (delete it to reclaim space)."
  exit 0
fi

for tool in git meson ninja valac pkg-config glib-compile-schemas; do
  command -v "$tool" >/dev/null || { echo "Missing $tool." >&2; missing=1; }
done
for mod in gtk4 granite-7 libadwaita-1 gee-0.8 gala x11 wayland-client; do
  pkg-config --exists "$mod" 2>/dev/null || { echo "Missing development files for $mod" >&2; missing=1; }
done
if [[ ${missing:-0} == 1 ]]; then
  echo 'Install build requirements with:' >&2
  echo '  sudo apt install git meson ninja-build valac libgtk-4-dev libgranite-7-dev libadwaita-1-dev libgee-0.8-dev libgala-dev libx11-dev libwayland-dev' >&2
  exit 1
fi

installed_version=$(dpkg-query -W -f='${Version}' io.elementary.dock 2>/dev/null || true)
if [[ $installed_version != 8.3.3* ]]; then
  echo "This patch targets io.elementary.dock 8.3.3.x; found ${installed_version:-none}." >&2
  exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/dock-drawers.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT
source_dir="$work_dir/source"
build_dir="$work_dir/build"

git init -q "$source_dir"
git -C "$source_dir" remote add origin https://github.com/elementary/dock.git
git -C "$source_dir" fetch -q --depth=1 origin "$commit"
git -C "$source_dir" checkout -q --detach FETCH_HEAD
git -C "$source_dir" apply "$patch"
git -C "$source_dir" apply "$startup_patch"

meson setup "$build_dir" "$source_dir" --prefix="$prefix" --buildtype=release >/dev/null
ninja -C "$build_dir" >/dev/null
test -x "$build_dir/src/io.elementary.dock"
glib-compile-schemas --strict --dry-run "$source_dir/data"
if [[ $mode == --build-only ]]; then
  echo 'Native dock build and schema validation passed; installed dock unchanged.'
  exit 0
fi
meson install -C "$build_dir" --no-rebuild >/dev/null
glib-compile-schemas "$prefix/share/glib-2.0/schemas"

# Per-user wrapper with automatic fallback to the stock dock.
mkdir -p "$(dirname "$wrapper")"
cat > "$wrapper" <<LAUNCHER
#!/bin/sh
# ElementaryOS_MSeries: run the patched dock (drawer slots) with a stock fallback.
# Delete this file (or run install-dock-drawers.sh --revert) and log out/in to revert.
flag="\$HOME/.cache/mseries-dock-failed"
patched="$patched"
stock="$stock"

use_stock() {
  logger -t mseries-dock "\$1; starting stock dock"
  exec "\$stock"
}

[ -e "\$flag" ] && use_stock "patched dock disabled by \$flag"
[ -x "\$patched" ] || use_stock "patched dock missing"
ldd "\$patched" 2>/dev/null | grep -q 'not found' && use_stock "patched dock has unresolved libraries"

# Forward session stops to the real dock and reap it before the wrapper exits.
# Otherwise Gala may restart a wrapper while the old dock still owns its D-Bus name.
child=
stop_dock() {
  trap '' HUP INT TERM
  child=\${child:-\$!}
  if [ -n "\$child" ]; then
    kill -TERM "\$child" 2>/dev/null || :
    wait "\$child" 2>/dev/null || :
  fi
  exit "\$1"
}
trap 'stop_dock 129' HUP
trap 'stop_dock 130' INT
trap 'stop_dock 143' TERM

start=\$(date +%s)
GSETTINGS_SCHEMA_DIR="$prefix/share/glib-2.0/schemas" "\$patched" &
child=\$!
wait "\$child"
rc=\$?
child=
trap - HUP INT TERM
# 129/130/137/143 = HUP/INT/KILL/TERM: the session or gala stopped the dock, not a dock fault.
case "\$rc" in 129|130|137|143) exit "\$rc" ;; esac
if [ "\$rc" -ne 0 ] && [ \$(( \$(date +%s) - start )) -lt 15 ]; then
  mkdir -p "\$(dirname "\$flag")" && : > "\$flag"
  logger -t mseries-dock "patched dock failed after under 15 s (rc=\$rc); disabled until \$flag is removed"
  exec "\$stock"
fi
exit "\$rc"
LAUNCHER
chmod 0755 "$wrapper"
# A successfully rebuilt dock gets another chance after a previous fallback.
rm -f "${HOME}/.cache/mseries-dock-failed"

echo "Installed the patched dock into $prefix."
echo "Pointed $wrapper at it (falls back to stock on failure)."
echo "Log out and back in, then click the chevron at the end of the dock to assign drawers."
echo "Revert:  bash mseries/install-dock-drawers.sh --revert"
