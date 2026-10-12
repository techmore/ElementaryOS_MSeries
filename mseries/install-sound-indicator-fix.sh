#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin="$(pkg-config --variable=indicatorsdir wingpanel-9)/libsound.so"
backup=/usr/local/lib/mseries/libsound.so.original
if [[ ${1:-} == --uninstall ]]; then
  sudo install -m644 "$backup" "$plugin"
  exit
fi
version=$(dpkg-query -W -f='${Version}' io.elementary.panel.sound)
[[ $version == 8.0.3* ]] || { echo "Patch targets sound indicator 8.0.3, found $version" >&2; exit 1; }
work=$(mktemp -d /tmp/mseries-sound-fix.XXXXXX)
trap 'rm -rf "$work"' EXIT
git init -q "$work/source"
git -C "$work/source" remote add origin https://github.com/elementary/wingpanel-indicator-sound.git
git -C "$work/source" fetch -q --depth=1 origin 8b7991c9156ac8127d27559506baea8e6fb72e5b
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/sound-icon-initialization.patch"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release
ninja -C "$work/build"
if ldd "$work/build/libsound.so" | rg -q 'not found'; then
  echo 'Missing runtime libraries; installed indicator preserved.' >&2
  exit 1
fi
if [[ ! -f $backup ]]; then sudo install -Dm644 "$plugin" "$backup"; fi
sudo install -m644 "$work/build/libsound.so" "$plugin"
echo 'Installed sound icon initialization and animation identity fixes. Reload Wingpanel to activate.'
