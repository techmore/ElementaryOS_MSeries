#!/usr/bin/env bash
# Builds quick-settings/AirPlayOutputs.vala into a tiny test window and renders it under xvfb with
# the fake receiver list (MSERIES_AIRPLAY_FAKE=1): no real audio, no windows on the real screen.
# Usage: test_airplay_outputs_render.sh OUT_PREFIX  -> OUT_PREFIX-expanded.png, OUT_PREFIX-clicked.png
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=${1:?output prefix}
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
valac --pkg gtk4 --pkg json-glib-1.0 -X -DGETTEXT_PACKAGE=\"test\" -o "$work/render" \
  "$here/../quick-settings/AirPlayOutputs.vala" "$here/render_airplay_outputs.vala" 2>&1 | grep -E 'error' || true
export MSERIES_AIRPLAY_FAKE=1 MSERIES_AIRPLAY_BIN="$here/../airplay/mseries-airplay-outputs"
export XDG_CONFIG_HOME="$work/cfg" GDK_BACKEND=x11 GSK_RENDERER=cairo
xvfb-run -a -s '-screen 0 800x600x24' "$work/render" "$out"
echo "saved state: $(cat "$work/cfg/mseries/airplay.json" 2>/dev/null | tr -d '\n ')"
