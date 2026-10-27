#!/usr/bin/env bash
# Hide the duplicate session Bluetooth icon, retaining its background services and greeter icon.
# Quick Settings must already include Bluetooth.vala before this installer is run.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin="$(pkg-config --variable=indicatorsdir wingpanel-9)/libbluetooth.so"
source "$repo/mseries/lib-backup.sh"
if [[ ${1:-} == --uninstall ]]; then
  mseries_restore "$plugin" io.elementary.panel.bluetooth
  echo 'Restored the standalone Bluetooth indicator. Reload Wingpanel to activate.'
  exit 0
fi
if [[ -n ${1:-} && ${1:-} != --build-only ]]; then
  echo 'Usage: install-bluetooth-control-center.sh [--build-only|--uninstall]' >&2
  exit 1
fi
version=$(dpkg-query -W -f='${Version}' io.elementary.panel.bluetooth)
[[ $version == 8.0.0* ]] || { echo "Patch targets Bluetooth indicator 8.0.0; found $version" >&2; exit 1; }
work=$(mktemp -d /tmp/mseries-bluetooth.XXXXXX)
trap 'rm -rf "$work"' EXIT
git init -q "$work/source"
git -C "$work/source" remote add origin https://github.com/elementary/panel-bluetooth.git
git -C "$work/source" fetch -q --depth=1 origin f67e65d09a8ab046f54895a326273dce5c491430
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/bluetooth-control-center.patch"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release
ninja -C "$work/build"
built="$work/build/libbluetooth.so"
if [[ ! -s $built ]] || ldd "$built" | grep -q 'not found'; then
  echo 'Bluetooth indicator build missing or unresolved dependencies; installed module preserved.' >&2
  exit 1
fi
if [[ ${1:-} == --build-only ]]; then
  echo 'Bluetooth indicator built and checked; nothing installed.'
  exit 0
fi
# Refuse to hide the old controls without their replacement being installed.
quick="$(dirname "$plugin")/libquick-settings.so"
if ! grep -aqF 'Bluetooth Settings' "$quick"; then
  echo 'Install Bluetooth controls in Quick Settings first.' >&2
  exit 1
fi
mseries_backup "$plugin" io.elementary.panel.bluetooth
mseries_install_indicator 644 "$built" "$plugin"
echo 'Bluetooth icon hidden in the session; background services and greeter retained. Reload Wingpanel to activate.'
