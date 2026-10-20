#!/usr/bin/env bash
# Install the M-Series size system (issue #332): CLI, ladder file and watcher.
# Adoption is opt-in: nothing on the desktop changes until the text size is
# changed from Quick Settings or with `mseries-ui-scale --set STEP`.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/ui-scale"
bin="$HOME/.local/bin/mseries-ui-scale"
data="${XDG_DATA_HOME:-$HOME/.local/share}/mseries/ui-scale"
unit="$HOME/.config/systemd/user/mseries-ui-scale.service"
if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-ui-scale.service 2>/dev/null || true
  rm -f "$bin" "$unit" "$data/size-system.json"
  systemctl --user daemon-reload
  echo 'Removed the size system; current text and dock sizes were left as they are.'
  exit 0
fi
install -Dm0755 "$src/mseries-ui-scale" "$bin"
install -Dm0644 "$src/size-system.json" "$data/size-system.json"
install -Dm0644 "$src/mseries-ui-scale.service" "$unit"
systemctl --user daemon-reload
systemctl --user enable mseries-ui-scale.service
systemctl --user restart mseries-ui-scale.service
"$bin" --status
