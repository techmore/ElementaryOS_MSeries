#!/usr/bin/env bash
# Stage the unified native menu. Never restart the owner's Wingpanel.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
activate=false
case ${1:-} in
  --uninstall)
    sudo rm -f "$indicators_dir/libmseries-t3.so" "$indicators_dir/../mseries-pending-indicators/libmseries-t3.so"
    echo 'Unified T3 module removed. Retained helpers, data and rollback modules. Loads at next login.'
    exit 0 ;;
  '') ;;
  --activate) activate=true ;;
  *) echo 'Usage: install-t3-wingpanel.sh [--uninstall|--activate]' >&2; exit 2 ;;
esac
build=$(mktemp -d "${TMPDIR:-/tmp}/mseries-t3-panel.XXXXXX")
trap 'rm -rf "$build"' EXIT
meson setup "$build" "$repo/mseries/t3-wingpanel" --prefix=/usr >/dev/null
ninja -C "$build" >/dev/null
bash "$repo/mseries/t3-wingpanel/test.sh" "$build" "$build/receipts"
install -d "$HOME/.local/bin"
for settings in codexbar-settings mseries-repobar-settings; do
  install -m0755 "$build/$settings" "$HOME/.local/bin/$settings.new"
  mv -f "$HOME/.local/bin/$settings.new" "$HOME/.local/bin/$settings"
done
# Wingpanel watches its directory and even loads .so.new files. Stage outside it.
pending="$indicators_dir/../mseries-pending-indicators"
sudo install -Dm0755 "$build/libmseries-t3.so" "$pending/libmseries-t3.so.new"
sudo mv -f "$pending/libmseries-t3.so.new" "$pending/libmseries-t3.so"
if "$activate"; then
  bash "$repo/mseries/activate-t3-panel.sh"
fi
sudo install -Dm0644 "$repo/mseries/t3-wingpanel/io.github.techmore.ClaudePantheonRs-symbolic.svg" \
  /usr/share/icons/hicolor/symbolic/apps/io.github.techmore.ClaudePantheonRs-symbolic.svg
echo 'Staged unified T3 menu outside Wingpanel discovery. Activation requires explicit --activate; default staging never reloads the panel.'
