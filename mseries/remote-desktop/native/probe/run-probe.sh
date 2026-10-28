#!/bin/bash
# Render the Remote Desktop screens headlessly (Xvfb + cairo renderer + fixture service).
# Usage: run-probe.sh BUILD_DIR OUT_DIR [light|dark]
set -euo pipefail
build=$(realpath "$1"); out=$2; scheme=${3:-light}
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
mkdir -p "$out"
home=$(mktemp -d); trap 'rm -rf "$home" 2>/dev/null || true' EXIT
theme=io.elementary.stylesheet.blueberry; [ "$scheme" = dark ] && theme="$theme:dark"
mkdir -p "$out/$scheme"
env -i PATH="$PATH" HOME="$home" LANG=C.UTF-8 GTK_THEME="$theme" GSK_RENDERER=cairo GDK_BACKEND=x11 \
  XDG_DATA_DIRS="$here/../data:/usr/local/share:/usr/share" \
  xvfb-run -a -s "-screen 0 800x1000x24" "$build/render-probe" "$out/$scheme"
ls "$out/$scheme"
