#!/usr/bin/env bash
# Shared migration boundary. A selected unified module owns panel presentation;
# legacy deploys may update their retained rollback copy but never recreate an icon.
t3_panel_module_target() {
  local directory=$1 module=$2
  if [[ -f "$directory/libmseries-t3.so" || -f "$directory/../mseries-pending-indicators/libmseries-t3.so" ]]; then
    printf '%s/../mseries-retired-indicators/%s\n' "$directory" "$module"
  else
    printf '%s/%s\n' "$directory" "$module"
  fi
}
