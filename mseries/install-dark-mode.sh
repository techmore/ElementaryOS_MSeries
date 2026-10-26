#!/usr/bin/env bash
# Install the universal dark-mode switch for the current user, plus an optional schedule timer.
#   install-dark-mode.sh              install the tool (mseries-dark-mode appearance light|dark|auto)
#   install-dark-mode.sh --schedule   apply Automatic at login and every 15 minutes (a one-shot timer also fires at each sunrise and sunset)
#   install-dark-mode.sh --uninstall  remove the tool and the timer (the current theme is left as is)
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin=$HOME/.local/bin/mseries-dark-mode
unit_dir=$HOME/.config/systemd/user

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-dark-mode.timer 2>/dev/null || true
  rm -f "$bin" "$unit_dir/mseries-dark-mode.service" "$unit_dir/mseries-dark-mode.timer"
  systemctl --user daemon-reload
  echo 'Removed mseries-dark-mode.'
  exit 0
fi

install -Dm0755 "$here/dark-mode/mseries-dark-mode" "$bin"
systemctl --user stop mseries-dark-mode-next.timer 2>/dev/null || true
if [[ ${1:-} == --schedule || -e "$unit_dir/mseries-dark-mode.service" || -e "$unit_dir/mseries-dark-mode.timer" ]]; then
  install -Dm0644 "$here/dark-mode/mseries-dark-mode.service" "$unit_dir/mseries-dark-mode.service"
  install -Dm0644 "$here/dark-mode/mseries-dark-mode.timer" "$unit_dir/mseries-dark-mode.timer"
  systemctl --user daemon-reload
fi
if [[ ${1:-} == --schedule ]]; then
  systemctl --user enable --now mseries-dark-mode.timer
fi
"$bin" status
