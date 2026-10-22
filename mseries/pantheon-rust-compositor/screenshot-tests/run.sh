#!/usr/bin/env bash
# Full-screen shortcut -> compositor rendering -> PNG, on a private display.
set -euo pipefail
: "${SCREENSHOT_TEST_BIN:?set the freshly built compositor binary}"
SCREENSHOT_TEST_BIN=$(realpath "$SCREENSHOT_TEST_BIN")
export SCREENSHOT_TEST_BIN
if [[ ${1:-} != --inside ]]; then
  scratch=$(mktemp -d /tmp/pantheon-capture-probe.XXXXXX)
  mkdir -p "$scratch"/{home,runtime,config,cache,data,bin}
  chmod 700 "$scratch/runtime"
  cat >"$scratch/bus.conf" <<'BUS'
<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>
BUS
  printf '#!/bin/sh\nprintf sound-requested >"$HOME/sound-requested"\n' >"$scratch/bin/canberra-gtk-play"
  chmod 755 "$scratch/bin/canberra-gtk-play"
  echo "Retaining synthetic capture receipt: $scratch"
  env -u WAYLAND_DISPLAY HOME="$scratch/home" XDG_RUNTIME_DIR="$scratch/runtime" \
    XDG_CONFIG_HOME="$scratch/config" XDG_CACHE_HOME="$scratch/cache" XDG_DATA_HOME="$scratch/data" \
    PATH="$scratch/bin:$PATH" CAPTURE_RECEIPT="$scratch" \
    dbus-run-session --config-file="$scratch/bus.conf" -- \
    xvfb-run -a -s '-screen 0 1280x800x24' bash "$0" --inside
  exit
fi
export GSETTINGS_BACKEND=memory GIO_USE_VFS=local GTK_A11Y=none
export PANTHEON_WAYLAND_DISPLAY=capture-test RUST_LOG=info NO_COLOR=1
"$SCREENSHOT_TEST_BIN" >"$CAPTURE_RECEIPT/compositor.log" 2>&1 &
compositor_pid=$!
trap 'kill "$compositor_pid" ${fixture_pid:-} 2>/dev/null || true' EXIT
for _ in $(seq 100); do
  [[ -S "$XDG_RUNTIME_DIR/capture-test" ]] && break
  kill -0 "$compositor_pid"
  sleep 0.1
done
window=""
for _ in $(seq 100); do
  window=$(xdotool search --onlyvisible --pid "$compositor_pid" | head -1) || true
  [[ -n $window ]] && break
  kill -0 "$compositor_pid"
  sleep 0.1
done
[[ -n $window ]]
GDK_BACKEND=wayland WAYLAND_DISPLAY=capture-test GSK_RENDERER=cairo \
  /usr/bin/python3 "$(dirname "$0")/fixture.py" >"$CAPTURE_RECEIPT/fixture.log" 2>&1 &
fixture_pid=$!
for _ in $(seq 100); do
  [[ -f "$CAPTURE_RECEIPT/fixture-ready" ]] && break
  kill -0 "$fixture_pid"
  sleep 0.1
done
[[ -f "$CAPTURE_RECEIPT/fixture-ready" ]]
sleep 0.2
xdotool windowfocus --sync "$window"
xdotool key --clearmodifiers super+shift+3
for _ in $(seq 100); do
  [[ -f "$HOME/sound-requested" ]] && break
  kill -0 "$compositor_pid"
  sleep 0.1
done
/usr/bin/python3 - "$HOME" <<'CHECK'
import pathlib, struct, sys
home = pathlib.Path(sys.argv[1])
files = list((home / 'Downloads/Screenshots').glob('*.png'))
assert len(files) == 1, files
header = files[0].read_bytes()[:24]
assert header[:8] == b'\x89PNG\r\n\x1a\n'
assert struct.unpack('>II', header[16:24]) == (1280, 800), header
assert files[0].stat().st_mode & 0o777 == 0o600
assert (home / 'sound-requested').exists()
from PIL import Image
image = Image.open(files[0]).convert('RGB')
red_y, blue_y = [], []
for y in range(image.height):
    for x in range(image.width):
        r, g, b = image.getpixel((x, y))
        if r > 180 and g < 80 and b < 80:
            red_y.append(y)
        if b > 180 and r < 80 and g < 80:
            blue_y.append(y)
assert len(red_y) > 1000 and len(blue_y) > 1000, 'fixture missing or channel conversion incorrect'
assert sum(red_y) / len(red_y) < sum(blue_y) / len(blue_y), 'screenshot is vertically inverted'

print('PASS: full-screen shortcut produced a private 1280x800 PNG and requested shutter sound')
CHECK
