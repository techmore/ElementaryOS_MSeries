#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin="$(pkg-config --variable=indicatorsdir wingpanel-9)/libkeyboard.so"
source "$repo/mseries/lib-backup.sh"
if [[ ${1:-} == --uninstall ]]; then
  mseries_restore "$plugin" io.elementary.panel.keyboard
  exit
fi
version=$(dpkg-query -W -f='${Version}' io.elementary.panel.keyboard)
[[ $version == 2.4.2* ]] || { echo "Patch targets keyboard indicator 2.4.2, found $version" >&2; exit 1; }
work=$(mktemp -d /tmp/mseries-keyboard-fix.XXXXXX)
trap 'rm -rf "$work"' EXIT
git init -q "$work/source"
git -C "$work/source" remote add origin https://github.com/elementary/panel-keyboard.git
git -C "$work/source" fetch -q --depth=1 origin 2d086e0177d7aa9a9e6aa4eb11fa7fb77c628c76
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/keyboard-popover-active.patch"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release
ninja -C "$work/build"
if ldd "$work/build/libkeyboard.so" | grep -q 'not found'; then
  echo 'Missing runtime libraries; installed indicator preserved.' >&2
  exit 1
fi
mseries_backup "$plugin" io.elementary.panel.keyboard
sudo install -m644 "$work/build/libkeyboard.so" "$plugin"
echo 'Installed keyboard indicator property fix. Reload Wingpanel to activate.'
