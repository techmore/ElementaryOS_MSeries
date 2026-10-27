#!/usr/bin/env bash
# Explicit activation only: invoke when the owner requests a Wingpanel reload.
set -euo pipefail
[[ $# == 0 ]] || { echo 'Usage: mseries-activate-t3-panel' >&2; exit 2; }
directory=$(pkg-config --variable=indicatorsdir wingpanel-9)
pending="$directory/../mseries-pending-indicators/libmseries-t3.so"
[[ -f $pending ]] || { echo 'No staged T3 panel module.' >&2; exit 1; }
# Stop before any directory event: the old and new widgets share GTypes/ABI names.
systemctl --user stop pantheon-wingpanel.service
trap 'systemctl --user start pantheon-wingpanel.service' EXIT
sudo install -d -m0755 "$directory/../mseries-retired-indicators"
for module in libcodexbar.so librepobar.so libclaude-pantheon.so; do
  if [[ -f "$directory/$module" ]]; then
    sudo mv -f "$directory/$module" "$directory/../mseries-retired-indicators/$module"
  fi
done
sudo install -m0755 "$pending" "$directory/libmseries-t3.so.new"
sudo mv -f "$directory/libmseries-t3.so.new" "$directory/libmseries-t3.so"
systemctl --user start pantheon-wingpanel.service
trap - EXIT
echo 'Activated the unified T3 panel with legacy modules retired.'
