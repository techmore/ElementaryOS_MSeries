#!/usr/bin/env bash
# Check the actual patched GTK layout without changing the desktop.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
git -C "$work_dir" init -q
git -C "$work_dir" remote add origin https://github.com/elementary/wingpanel.git
git -C "$work_dir" fetch -q --depth=1 origin 6b8ae0453b1fd6dc07bd246642998011f04b2125
git -C "$work_dir" checkout -q --detach FETCH_HEAD
git -C "$work_dir" apply "$repo/mseries/patches/wingpanel-full-height.patch"
valac --pkg gtk4 "$work_dir/src/Widgets/NotchLayout.vala" \
  "$repo/mseries/display-space/test-notch-layout.vala" -o "$work_dir/test-notch-layout" -X -lm
GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a -s '-screen 0 1920x1080x24' "$work_dir/test-notch-layout"
