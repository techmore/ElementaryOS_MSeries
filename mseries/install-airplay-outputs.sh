#!/usr/bin/env bash
# Install the AirPlay Outputs chooser (dot per receiver) for the current user. Needs AirPlay
# discovery (install-airplay-discovery.sh). Does not touch or restart PipeWire.
#   bash mseries/install-airplay-outputs.sh              # install
#   bash mseries/install-airplay-outputs.sh --uninstall  # remove and stop the AirPlay Group
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
src=$root/airplay bin=$HOME/.local/bin auto=$HOME/.config/autostart apps=$HOME/.local/share/applications
if [[ ${1:-} == --uninstall ]]; then
  systemctl --user stop mseries-airplay-group 2>/dev/null || true
  rm -f "$bin/mseries-airplay-outputs" "$bin/airplay_core.py" "$auto/mseries-airplay-outputs-apply.desktop" "$apps/mseries-airplay-outputs.desktop"
  echo 'Removed AirPlay Outputs (saved choice in ~/.config/mseries/airplay.json is kept).'; exit 0
fi
dpkg -s python3-gi >/dev/null 2>&1 || sudo apt-get install -y python3-gi
mkdir -p "$bin" "$auto" "$apps"
install -m 755 "$src/mseries-airplay-outputs" "$bin/mseries-airplay-outputs"
install -m 644 "$src/airplay_core.py" "$bin/airplay_core.py"
sed "s#@BIN@#$bin#" "$src/mseries-airplay-outputs.desktop" > "$apps/mseries-airplay-outputs.desktop"
sed "s#@BIN@#$bin#" "$src/mseries-airplay-outputs-apply.desktop" > "$auto/mseries-airplay-outputs-apply.desktop"
update-desktop-database "$apps" 2>/dev/null || true
echo 'Installed. Open "AirPlay Outputs" from the app menu, or: mseries-airplay-outputs list'
