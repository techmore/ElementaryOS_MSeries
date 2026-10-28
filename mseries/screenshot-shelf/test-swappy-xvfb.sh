#!/usr/bin/env bash
# Local test for the patched swappy (needs Xvfb, xdotool, ImageMagick, poppler-utils).
# Not run in CI: it needs the built binary, which comes from a network clone.
#   bash mseries/screenshot-shelf/test-swappy-xvfb.sh [path/to/swappy]
set -euo pipefail
swappy=${1:-$HOME/.local/bin/swappy}
[[ -x $swappy ]] || { echo "no swappy at $swappy; run build-swappy.sh" >&2; exit 1; }
for tool in xvfb-run xdotool convert pdfinfo; do command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 1; }; done
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
convert -size 800x500 gradient:white-steelblue "$work/in.png"
export SWAPPY=$swappy WORK=$work
xvfb-run -a -s "-screen 0 1280x800x24" bash -c '
  set -euo pipefail
  export HOME=$WORK/home XDG_CONFIG_HOME=$WORK/home/.config GTK_USE_PORTAL=0 GDK_BACKEND=x11 NO_AT_BRIDGE=1 GSETTINGS_BACKEND=memory
  mkdir -p "$HOME"; cd "$HOME"
  "$SWAPPY" -f "$WORK/in.png" -o "$WORK/in (markup).png" >"$WORK/swappy.log" 2>&1 &
  pid=$!
  sleep 3
  xdotool key --clearmodifiers ctrl+shift+p; sleep 2
  xdotool key --clearmodifiers ctrl+a; sleep 1
  xdotool type --delay 60 "$HOME/out.pdf"; sleep 1
  xdotool key Return; sleep 3
  # Close button: the window must be closable; Ctrl+W is the keyboard path.
  xdotool key --clearmodifiers ctrl+w; sleep 2
  if kill -0 $pid 2>/dev/null; then echo "FAIL: swappy still running after Ctrl+W" >&2; kill $pid; exit 1; fi
  [[ -f $HOME/out.pdf ]] || { echo "FAIL: no PDF written" >&2; exit 1; }
  info=$(pdfinfo "$HOME/out.pdf")
  grep -q "^Pages: *1" <<<"$info" || { echo "FAIL: expected one page" >&2; echo "$info" >&2; exit 1; }
  read -r w h < <(sed -n "s/^Page size: *\([0-9.]*\) x \([0-9.]*\) pts.*/\1 \2/p" <<<"$info")
  awk -v w="$w" -v h="$h" "BEGIN{exit !(w>h)}" || { echo "FAIL: 800x500 image should give a landscape page ($w x $h)" >&2; exit 1; }
  echo "$info" | grep -E "^(Pages|Page size)"
  echo "PASS"
'
