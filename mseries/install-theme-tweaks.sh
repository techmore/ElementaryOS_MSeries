#!/usr/bin/env bash
# Softer blueberry/strawberry accent colours, larger window corners and a muted Ghostty palette.
#   bash mseries/install-theme-tweaks.sh              # install (existing files are backed up as *.mseries-backup)
#   bash mseries/install-theme-tweaks.sh --uninstall  # remove the tweaks / restore backups
# Apps pick up the colours the next time they start; the panel is reloaded for you.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src=$repo/mseries/theme

pairs=(
  "$src/gtk-4.0.css|$HOME/.config/gtk-4.0/gtk.css"
  "$src/gtk-3.0.css|$HOME/.config/gtk-3.0/gtk.css"
  "$src/ghostty.config|$HOME/.config/ghostty/config.ghostty"
)

for pair in "${pairs[@]}"; do
  from=${pair%%|*}; to=${pair##*|}
  if [[ ${1:-} == --uninstall ]]; then
    if [[ -f $to.mseries-backup ]]; then mv -f "$to.mseries-backup" "$to"; else rm -f "$to"; fi
  else
    mkdir -p "$(dirname "$to")"
    if [[ -f $to && ! -f $to.mseries-backup ]] && ! cmp -s "$from" "$to"; then cp -a "$to" "$to.mseries-backup"; fi
    install -m 0644 "$from" "$to"
  fi
done

pkill -x io.elementary.w 2>/dev/null || true   # Gala respawns the panel with the new colours
echo 'Done. Restart open apps to see the new colours; new Ghostty windows use the new palette.'
