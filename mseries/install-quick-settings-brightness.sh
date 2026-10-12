#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin="$(pkg-config --variable=indicatorsdir wingpanel-9)/libquick-settings.so"
backup=/usr/local/lib/mseries/libquick-settings.so.original
if [[ ${1:-} == --uninstall ]]; then
  sudo install -m644 "$backup" "$plugin"
  echo 'Original Quick Settings restored. Reload Wingpanel to activate.'
  exit
fi
version=$(dpkg-query -W -f='${Version}' io.elementary.quick-settings)
[[ $version == 1.4.0* ]] || { echo "Patch targets Quick Settings 1.4.0, found $version" >&2; exit 1; }
work=$(mktemp -d /tmp/mseries-quick-settings.XXXXXX)
trap 'rm -rf "$work"' EXIT
git init -q "$work/source"
git -C "$work/source" remote add origin https://github.com/elementary/quick-settings.git
git -C "$work/source" fetch -q --depth=1 origin fb721d4b5640a2a25ae011370c8fe8aaff8d93f4
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/quick-settings-brightness.patch"
install -m644 "$repo/mseries/quick-settings/ScreenBrightness.vala" "$work/source/src/Widgets/ScreenBrightness.vala"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release
ninja -C "$work/build"
if ldd "$work/build/src/libquick-settings.so" | rg -q 'not found'; then
  echo 'Missing runtime libraries; installed indicator preserved.' >&2
  exit 1
fi
if [[ ! -f $backup ]]; then sudo install -Dm644 "$plugin" "$backup"; fi
sudo install -m644 "$work/build/src/libquick-settings.so" "$plugin"
echo 'Installed screen brightness below the gear-menu toggles. Reload Wingpanel to activate.'
