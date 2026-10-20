#!/usr/bin/env bash
# Check the real scaled IndicatorBar in an isolated GTK display.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT
git -C "$test_dir" init -q
git -C "$test_dir" fetch -q --depth=1 https://github.com/elementary/wingpanel.git 6b8ae0453b1fd6dc07bd246642998011f04b2125
git -C "$test_dir" checkout -q --detach FETCH_HEAD
for patch in wingpanel-full-height wingpanel-startup-layout wingpanel-content-scale; do
    git -C "$test_dir" apply "$repo/mseries/patches/$patch.patch"
done
valac --pkg gtk4 --pkg granite-7 "$test_dir/src/Widgets/IndicatorBar.vala" \
    "$repo/mseries/display-space/test-panel-scale.vala" -o "$test_dir/test-panel-scale" -X -lm >"$test_dir/build.log" 2>&1 || { cat "$test_dir/build.log"; exit 1; }
G_DEBUG=fatal-criticals GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a "$test_dir/test-panel-scale"
