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
# Screen-share section (the pair of eyes): status, watchers, links and login inside the top-right menu.
for f in ShareState ShareClient SharePanel; do install -m644 "$repo/mseries/share-eyes-wingpanel/$f.vala" "$work/source/src/Widgets/$f.vala"; done
sed -i "s|    'Widgets' / 'ChargeLimit.vala',|    'Widgets' / 'ChargeLimit.vala',\n    'Widgets' / 'ShareState.vala',\n    'Widgets' / 'ShareClient.vala',\n    'Widgets' / 'SharePanel.vala',|; s|        accountsservice_dep\$|        accountsservice_dep,\n        dependency('json-glib-1.0'),\n        dependency('libsoup-3.0')|" "$work/source/src/meson.build"
sed -i 's|            main_box.append (new ChargeLimit ());|            main_box.append (new ChargeLimit ());\n            main_box.append (new MSeries.SharePanel () { spawn_dock_app = true, notify_waiting = true });|' "$work/source/src/PopoverWidget.vala"
grep -q SharePanel "$work/source/src/PopoverWidget.vala" && grep -q libsoup "$work/source/src/meson.build" && grep -q "'SharePanel.vala'" "$work/source/src/meson.build" \
  || { echo 'could not wire the share section into Quick Settings' >&2; exit 1; }
install -m644 "$repo/mseries/share-eyes-wingpanel/icons/eyes.svg" "$work/mseries-share-eyes-symbolic.svg"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release
ninja -C "$work/build"
if ldd "$work/build/src/libquick-settings.so" | grep -q 'not found'; then
  echo 'Missing runtime libraries; installed indicator preserved.' >&2
  exit 1
fi
mseries_backup "$plugin" io.elementary.quick-settings
sudo install -m644 "$work/build/src/libquick-settings.so" "$plugin"
# Dock app (eyes in the dock while a share is offered): per-user install, no sudo.
meson setup "$work/share-app" "$repo/mseries/share-eyes-wingpanel" --prefix="$HOME/.local" --buildtype=release >/dev/null
ninja -C "$work/share-app" >/dev/null
install -Dm755 "$work/share-app/mseries-share-eyes" "$HOME/.local/bin/mseries-share-eyes"
install -Dm644 "$repo/mseries/share-eyes-wingpanel/io.github.techmore.ShareEyes.desktop" "$HOME/.local/share/applications/io.github.techmore.ShareEyes.desktop"
install -Dm644 "$repo/mseries/share-eyes-wingpanel/icons/eyes.svg" "$HOME/.local/share/icons/hicolor/scalable/apps/mseries-share-eyes-symbolic.svg"
sudo install -m644 "$work/mseries-share-eyes-symbolic.svg" /usr/share/icons/hicolor/scalable/apps/mseries-share-eyes-symbolic.svg
echo 'Installed the screen-share section (shown only while the share demo runs), keyboard brightness, screen brightness and the charge-limit switch below the gear-menu toggles (the switch needs install-power.sh for its polkit action). Reload Wingpanel to activate.'
