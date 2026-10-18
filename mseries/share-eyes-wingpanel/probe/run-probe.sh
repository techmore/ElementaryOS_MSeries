#!/bin/bash
# Render the eyes headlessly (Xvfb + cairo + fake HOME/runtime dir/icon dir). Usage: run-probe.sh BUILD_DIR OUT_DIR
set -euo pipefail
build=$(realpath "$1"); out=$2; here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$out"; home=$(mktemp -d); trap 'rm -rf "$home" 2>/dev/null || true' EXIT
mkdir -p "$home/run/rupert-share" "$home/share/icons/hicolor/scalable/apps"
cp "$here/icons/eyes.svg" "$home/share/icons/hicolor/scalable/apps/mseries-share-eyes-symbolic.svg"
run() { # name, state-json
  printf '%s' "$2" > "$home/run/rupert-share/state.json"
  env -i PATH="$PATH" HOME="$home" XDG_RUNTIME_DIR="$home/run" XDG_DATA_DIRS="$home/share:/usr/share" LANG=C.UTF-8 \
    GTK_THEME=io.elementary.stylesheet.blueberry GSK_RENDERER=cairo GDK_BACKEND=x11 \
    xvfb-run -a -s "-screen 0 400x200x24" "$build/render-probe" "$out/$1.png"
}
now=$(date +%s)
run live "{\"live\":true,\"viewers\":1,\"updated\":$now}"
run stale "{\"live\":true,\"viewers\":1,\"updated\":$((now-60))}"
