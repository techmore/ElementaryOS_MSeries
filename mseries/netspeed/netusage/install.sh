#!/bin/sh
# Installs the netusage logger as a systemd user service and starts it.
set -e
here=$(cd "$(dirname "$0")" && pwd)
mode=${1:-}
if [[ $mode != --user-only ]]; then
  sudo install -Dm644 "$here/49-mseries-netusage.rules" /etc/polkit-1/rules.d/49-mseries-netusage.rules
fi
install -Dm755 "$here/netusage.py" "$HOME/.local/lib/netusage/netusage.py"
install -Dm644 "$here/netusage.service" "$HOME/.config/systemd/user/netusage.service"
systemctl --user daemon-reload
systemctl --user enable netusage.service
systemctl --user restart netusage.service
