#!/usr/bin/env bash
# Docked lid mode: with a USB4 dock attached, closing the lid locks the screen and switches the panel
# off instead of retrying a suspend the dock's driver refuses. Undocked, the lid still suspends.
#   bash mseries/install-docked-lid.sh              # install and start (user service, no root)
#   bash mseries/install-docked-lid.sh --uninstall  # remove it
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bin=$HOME/.local/libexec/mseries-docked-lid
unit=$HOME/.config/systemd/user/mseries-docked-lid.service

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-docked-lid.service 2>/dev/null || true
  rm -f "$bin" "$unit"
  systemctl --user daemon-reload
  echo 'Removed. The lid goes back to plain suspend.'
  exit 0
fi

install -Dm755 "$repo/mseries/docked-lid/mseries-docked-lid" "$bin"
mkdir -p "$(dirname "$unit")"
cat > "$unit" <<UNIT
[Unit]
Description=Docked lid mode: lock instead of suspend while a USB4 dock is attached

[Service]
ExecStart=/usr/bin/python3 -I $bin
Restart=on-failure
RestartSec=5
Nice=10

[Install]
WantedBy=default.target
UNIT
systemctl --user daemon-reload
systemctl --user enable --now mseries-docked-lid.service
sleep 1
"$bin" --status
