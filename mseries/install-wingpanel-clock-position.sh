#!/bin/bash
# Rebuild Wingpanel so the right-side "clockright" indicator sits after Alerts
# (Messages) and before Quick Settings. Requires install-clockright-wingpanel.sh.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
patch="$repo/mseries/patches/wingpanel-clockright-order.patch"
bin=/usr/bin/io.elementary.wingpanel
# Matches the packaged daily build; keep in step with the installed package.
commit=6b8ae04

if [[ ${1:-} == --uninstall ]]; then
  [[ -f $bin.orig ]] || { echo "No $bin.orig backup found." >&2; exit 1; }
  sudo mv "$bin.orig" "$bin"
  pkill -f '^io.elementary.wingpanel' || true
  echo 'Restored the packaged Wingpanel.'
  exit 0
fi

for tool in git meson ninja valac; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo '  sudo apt install git meson ninja-build valac libwingpanel-9-dev' >&2
    exit 1
  }
done

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/wingpanel-clock-position.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
git clone -q https://github.com/elementary/wingpanel.git "$build_dir/src"
git -C "$build_dir/src" checkout -q "$commit"
git -C "$build_dir/src" apply "$patch"
meson setup "$build_dir/build" "$build_dir/src" --prefix=/usr
ninja -C "$build_dir/build"

[[ -f $bin.orig ]] || sudo cp "$bin" "$bin.orig"
sudo install -m755 "$build_dir/build/src/io.elementary.wingpanel" "$bin"
pkill -f '^io.elementary.wingpanel' || true
echo 'Installed the reordered Wingpanel; it restarts automatically.'
