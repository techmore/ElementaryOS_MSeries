#!/usr/bin/env bash
# Put the CodexBar Wingpanel indicator in the left group, clear of the notch.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
binary=/usr/bin/io.elementary.wingpanel
MSERIES_BACKUP_DIR=/usr/local/lib/mseries/full-height
source "$repo/mseries/lib-backup.sh"
commit=6b8ae0453b1fd6dc07bd246642998011f04b2125
mode=${1:-install}

if [[ $mode == --uninstall ]]; then
  mseries_restore "$binary" io.elementary.wingpanel
  echo 'Restored the previous Wingpanel binary. Log out and back in to reload it.'
  exit 0
fi

if [[ $mode != install && $mode != --build-only ]]; then
  echo "Usage: $0 [--build-only|--uninstall]" >&2
  exit 2
fi

for tool in git meson ninja valac msgfmt pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install Wingpanel build requirements with:" >&2
    echo '  sudo apt install git meson ninja-build valac gettext libmutter-18-dev libgala-dev libwingpanel-9-dev libgranite-7-dev libgee-0.8-dev libgtk-4-dev' >&2
    exit 1
  }
done

installed_version=$(dpkg-query -W -f='${Version}' io.elementary.wingpanel 2>/dev/null || true)
if [[ $installed_version != 8.0.4* ]]; then
  echo "This notch placement patch targets Wingpanel 8.0.4; found ${installed_version:-unknown}." >&2
  exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/wingpanel-codexbar-left.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT
source_dir="$work_dir/source"
build_dir="$work_dir/build"
stage_dir="$work_dir/stage"

git init -q "$source_dir"
git -C "$source_dir" remote add origin https://github.com/elementary/wingpanel.git
git -C "$source_dir" fetch -q --depth=1 origin "$commit"
git -C "$source_dir" checkout -q --detach FETCH_HEAD
git -C "$source_dir" apply --check --ignore-space-change "$repo/mseries/patches/wingpanel-full-height.patch"
git -C "$source_dir" apply --ignore-space-change "$repo/mseries/patches/wingpanel-full-height.patch"
# Keep the optional right-side clock ordering when that companion is installed.
git -C "$source_dir" apply --check "$repo/mseries/patches/wingpanel-clockright-order.patch"
git -C "$source_dir" apply "$repo/mseries/patches/wingpanel-clockright-order.patch"

meson setup "$build_dir" "$source_dir" --prefix=/usr --buildtype=release
ninja -C "$build_dir"
meson test -C "$build_dir" --print-errorlogs
DESTDIR="$stage_dir" meson install -C "$build_dir"
staged_binary="$stage_dir/usr/bin/io.elementary.wingpanel"
test -x "$staged_binary"
if ldd "$staged_binary" | grep -q 'not found'; then
  echo 'The staged Wingpanel binary has unresolved libraries; leaving the installed panel unchanged.' >&2
  exit 1
fi

if [[ $mode == --build-only ]]; then
  echo 'CodexBar left-group Wingpanel build and tests passed; installed panel was not changed.'
  exit 0
fi

mseries_backup "$binary" io.elementary.wingpanel
sudo install -m 0755 "$staged_binary" "$binary"
echo 'Installed the M-series native clock and CodexBar layout, clear of the notch. Log out and back in to reload Wingpanel.'
