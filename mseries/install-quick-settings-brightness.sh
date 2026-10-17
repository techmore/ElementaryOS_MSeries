#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin="$(pkg-config --variable=indicatorsdir wingpanel-9)/libquick-settings.so"
source "$repo/mseries/lib-backup.sh"
if [[ ${1:-} == --uninstall ]]; then
  mseries_restore "$plugin" io.elementary.quick-settings
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
install -m644 "$repo/mseries/quick-settings/KeyboardBrightness.vala" "$work/source/src/Widgets/KeyboardBrightness.vala"
install -m644 "$repo/mseries/quick-settings/ChargeLimit.vala" "$work/source/src/Widgets/ChargeLimit.vala"
git -C "$work/source" apply "$repo/mseries/patches/quick-settings-audio-output.patch"
install -m644 "$repo/mseries/quick-settings/AudioOutputModel.vala" "$work/source/src/Widgets/AudioOutputModel.vala"
install -m644 "$repo/mseries/quick-settings/AudioOutput.vala" "$work/source/src/Widgets/AudioOutput.vala"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release
ninja -C "$work/build"
if ldd "$work/build/src/libquick-settings.so" | grep -q 'not found'; then
  echo 'Missing runtime libraries; installed indicator preserved.' >&2
  exit 1
fi
mseries_backup "$plugin" io.elementary.quick-settings
sudo install -m644 "$work/build/src/libquick-settings.so" "$plugin"
echo 'Installed keyboard brightness, screen brightness and the charge-limit switch and the Sound Output list (built-in, Bluetooth, AirPlay) below the gear-menu toggles (the switch needs install-power.sh for its polkit action; AirPlay needs install-airplay-discovery.sh). Reload Wingpanel to activate.'
