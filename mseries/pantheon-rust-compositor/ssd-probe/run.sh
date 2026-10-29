#!/usr/bin/env bash
# Server-side frames for X11 windows (decorations.rs), on a private display.
#
# Runs pantheon-compositor nested inside a virtual X display with a private
# runtime directory, D-Bus session and GSettings keyfile, so it never touches
# the live desktop. A plain GTK 3 X11 window (it asks the window manager for a
# frame, like WiFiman Desktop or xterm) must get a title bar that drags, resize
# bands that respect its 420x460 minimum, a maximize button, double-click
# restore and a close button. A GTK 3 header-bar window must get no frame and
# still move through _NET_WM_MOVERESIZE.
#
#   bash run.sh [path/to/pantheon-compositor]     (KEEP=<dir> keeps the log and screenshots)
#
# Needs: xvfb-run, dbus-run-session, xdotool, ImageMagick, python3-gi (GTK 3), Xwayland.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
target_dir=$(cd "$here/../../../rust" && cargo metadata --format-version 1 --no-deps 2>/dev/null \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["target_directory"])' 2>/dev/null || echo "$here/../../../rust/target")
binary=$(realpath "${1:-$target_dir/debug/pantheon-compositor}")
[[ -x $binary ]] || { echo "build it first: cargo build -p pantheon-compositor (or pass a path)" >&2; exit 2; }
for tool in xvfb-run dbus-run-session xdotool convert import python3 Xwayland; do
  command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 2; }
done
out=${KEEP:-$(mktemp -d)}
mkdir -p "$out"
BIN=$binary PROBE_DIR=$here OUT=$out \
xvfb-run -a -s "-screen 0 1440x900x24" dbus-run-session -- bash -c '
  set -u
  export HOST_DISPLAY=$DISPLAY
  rt=$(mktemp -d); chmod 700 "$rt"; export XDG_RUNTIME_DIR=$rt
  # A fixed button layout (the owner'"'"'s macOS-style one) through a private keyfile.
  export XDG_CONFIG_HOME=$rt/config GSETTINGS_BACKEND=keyfile
  mkdir -p "$XDG_CONFIG_HOME/glib-2.0/settings"
  printf "[org/gnome/desktop/wm/preferences]\nbutton-layout='"'"'close,minimize,maximize:'"'"'\n" \
    >"$XDG_CONFIG_HOME/glib-2.0/settings/keyfile"
  log=$OUT/compositor.log
  env -u WAYLAND_DISPLAY RUST_LOG=${RUST_LOG:-info} NO_COLOR=1 "$BIN" --backend nested >"$log" 2>&1 &
  comp=$!; export COMP_PID=$comp
  xdisplay=
  for _ in $(seq 1 80); do
    xdisplay=$(grep -o "display_number=[0-9]*" "$log" | head -1 | cut -d= -f2 || true)
    [ -n "$xdisplay" ] && break
    sleep 0.25
  done
  [ -n "$xdisplay" ] || { echo "RESULT FAIL XWayland never became ready"; tail -5 "$log"; kill $comp; exit 3; }
  export XDISPLAY=:$xdisplay
  sleep 1
  timeout 120 python3 -W ignore "$PROBE_DIR/probe.py"; status=$?
  kill $comp 2>/dev/null || true; wait $comp 2>/dev/null || true; rm -rf "$rt"
  exit $status'
status=$?
echo "log and screenshots: $out"
exit $status
