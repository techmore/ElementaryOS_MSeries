#!/usr/bin/env bash
# Nested snap regression. Starts its own D-Bus session and Xvfb; never targets
# the live desktop. Build with --features gesture-probe and set SNAP_TEST_BIN.
set -euo pipefail
if [[ ${1:-} != --inside ]]; then
  exec env -u WAYLAND_DISPLAY dbus-run-session -- xvfb-run -a -s '-screen 0 1280x800x24' bash "$0" --inside
fi
: "${SNAP_TEST_BIN:?build with --features gesture-probe and set SNAP_TEST_BIN}"
: "${SNAP_TEST_OUT:?set a receipt directory}"
[[ -n ${DISPLAY:-} && -z ${WAYLAND_DISPLAY:-} ]] || { echo 'needs an isolated X display'; exit 1; }
mkdir -p "$SNAP_TEST_OUT"
SNAP_TEST_OUT=$(realpath "$SNAP_TEST_OUT")
RUNTIME=$(mktemp -d /tmp/mseries-snap.XXXXXX)
chmod 700 "$RUNTIME"
trap 'kill ${compositor_pid:-} 2>/dev/null || true; rm -rf "$RUNTIME"' EXIT
export XDG_RUNTIME_DIR="$RUNTIME" XDG_CONFIG_HOME="$RUNTIME/config" XDG_CACHE_HOME="$RUNTIME/cache"
export GSK_RENDERER=cairo GSETTINGS_BACKEND=memory GTK_A11Y=none GTK_USE_PORTAL=0 RUST_LOG=info NO_COLOR=1
export PANTHEON_WAYLAND_DISPLAY=snap-check
"$SNAP_TEST_BIN" > "$SNAP_TEST_OUT/compositor.log" 2>&1 &
compositor_pid=$!
for _ in $(seq 100); do [[ -S $RUNTIME/snap-check && -S $RUNTIME/gesture-probe ]] && break; sleep 0.1; done
[[ -S $RUNTIME/gesture-probe ]]
GDK_BACKEND=wayland WAYLAND_DISPLAY=snap-check \
  python3 "$(dirname "$0")/check-snap.py" "$RUNTIME/gesture-probe" "$SNAP_TEST_OUT" "$(dirname "$0")/fixture.py"
