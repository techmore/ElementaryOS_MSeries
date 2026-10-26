#!/usr/bin/env bash
# Apply the M-series changes to a pinned elementary/quick-settings checkout, in
# order: brightness and charge limit, Sound Output (with AirPlay), Bluetooth,
# card layout, text-size ladder. Shared by the factory image (build-quick-settings) and the
# plugin package (mseries/debs/build.sh) so the two cannot drift. The desktop
# installer (install-quick-settings-brightness.sh) applies the same steps and
# then adds per-user extras (Share Eyes, AirDrop).
#
#   bash mseries/quick-settings/prepare-source.sh REPO_ROOT SOURCE_DIR
set -euo pipefail
root=${1:?usage: prepare-source.sh REPO_ROOT SOURCE_DIR}
src=${2:?usage: prepare-source.sh REPO_ROOT SOURCE_DIR}
widgets=$src/src/Widgets

git -C "$src" apply "$root/mseries/patches/quick-settings-brightness.patch"
for f in ScreenBrightness KeyboardBrightness ChargeLimit; do
  install -m 0644 "$root/mseries/quick-settings/$f.vala" "$widgets/$f.vala"
done
git -C "$src" apply "$root/mseries/patches/quick-settings-audio-output.patch"
for f in AudioOutputModel AudioOutput AirPlayOutputs; do
  install -m 0644 "$root/mseries/quick-settings/$f.vala" "$widgets/$f.vala"
done
git -C "$src" apply "$root/mseries/patches/quick-settings-bluetooth.patch"
install -m 0644 "$root/mseries/quick-settings/Bluetooth.vala" "$widgets/Bluetooth.vala"
git -C "$src" apply "$root/mseries/patches/quick-settings-layout.patch"
install -m 0644 "$root/mseries/quick-settings/Controls.vala" "$widgets/Controls.vala"
install -m 0644 "$root/mseries/quick-settings/Appearance.vala" "$widgets/Appearance.vala"
# Text size steps along the size-system ladder (mseries/ui-scale/size-system.json).
install -m 0644 "$root/mseries/quick-settings/TextScale.vala" "$widgets/TextScale.vala"
