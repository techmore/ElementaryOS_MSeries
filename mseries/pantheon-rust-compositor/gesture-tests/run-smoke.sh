#!/usr/bin/env bash
# Starts its own D-Bus session and Xvfb; never targets the live desktop.
set -euo pipefail
if [[ ${1:-} != --inside ]]; then
  exec env -u WAYLAND_DISPLAY dbus-run-session -- xvfb-run -a -s '-screen 0 1280x800x24' bash "$0" --inside
fi
: "${GESTURE_TEST_BIN:?build with --features gesture-probe and set GESTURE_TEST_BIN}"
: "${GESTURE_TEST_OUT:?set a receipt directory}"
[[ -n ${DISPLAY:-} && -z ${WAYLAND_DISPLAY:-} ]] || { echo 'needs an isolated X display'; exit 1; }
mkdir -p "$GESTURE_TEST_OUT"
GESTURE_TEST_OUT=$(realpath "$GESTURE_TEST_OUT")
RUNTIME=$(mktemp -d /tmp/mseries-gesture.XXXXXX)
chmod 700 "$RUNTIME"
trap 'kill ${fixture_pid:-} ${compositor_pid:-} 2>/dev/null || true; rm -rf "$RUNTIME"' EXIT
export XDG_RUNTIME_DIR="$RUNTIME" XDG_CONFIG_HOME="$RUNTIME/config" XDG_CACHE_HOME="$RUNTIME/cache"
export GSK_RENDERER=cairo GSETTINGS_BACKEND=memory GTK_A11Y=none GTK_USE_PORTAL=0 RUST_LOG=info
export PANTHEON_WAYLAND_DISPLAY=gesture-smoke
"$GESTURE_TEST_BIN" > "$GESTURE_TEST_OUT/compositor.log" 2>&1 &
compositor_pid=$!
for _ in $(seq 100); do [[ -S $RUNTIME/gesture-smoke && -S $RUNTIME/gesture-probe ]] && break; sleep 0.1; done
[[ -S $RUNTIME/gesture-probe ]]
GDK_BACKEND=wayland WAYLAND_DISPLAY=gesture-smoke python3 "$(dirname "$0")/fixture.py" > "$GESTURE_TEST_OUT/fixture.log" 2>&1 &
fixture_pid=$!
sleep 2
send() { python3 - "$RUNTIME/gesture-probe" "$@" <<'PY'
import socket,sys
with socket.socket(socket.AF_UNIX,socket.SOCK_DGRAM) as s:
 s.sendto(' '.join(sys.argv[2:]).encode(),sys.argv[1])
PY
}
shot() { ffmpeg -nostdin -loglevel error -f x11grab -video_size 1280x800 -i "$DISPLAY" -frames:v 1 -update 1 -y "$GESTURE_TEST_OUT/$1.png"; }
send move 1
send workspace 0
sleep 0.3
send status
shot workspace-start
send begin
send update -180 0
sleep 0.15
shot workspace-half
send end
sleep 0.8
send status
shot workspace-complete
send workspace 0
send begin
send update -180 0
send cancel
sleep 0.8
send status
shot workspace-cancel
send begin
send update 180 0
sleep 0.1
shot workspace-edge
send end
sleep 0.8
send status
send workspace 1
send move 0
send workspace 0
sleep 0.2
shot overview-start
send begin
send update 0 -180
sleep 0.1
shot overview-half
send cancel
sleep 0.8
send status
send begin
send update 0 -250
send end
sleep 0.8
send status
shot overview-complete
send begin
send update 0 180
sleep 0.1
shot overview-close-half
send cancel
sleep 0.8
send status
send begin
send update 0 250
send end
sleep 0.8
send status
shot overview-closed
# An interrupted spring must not commit a stale action.
send begin
send update -200 0
send end
send reset
sleep 0.8
send status
send animations off
send begin
send update -200 0
send end
send status
sleep 0.1
python3 "$(dirname "$0")/check-receipts.py" "$GESTURE_TEST_OUT"
