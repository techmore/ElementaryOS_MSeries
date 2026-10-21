#!/usr/bin/env bash
# Idle monitor, idle inhibitor and power-save checks for pantheon-compositor.
#
# Runs the compositor nested inside a virtual X display with a private runtime
# directory and D-Bus session, so it never touches the live desktop (or the
# live session's gsd-power, which would otherwise find this IdleMonitor).
#
#   bash run.sh [path/to/pantheon-compositor]
#
# Needs: xvfb-run, dbus-run-session, xdotool, python3-gi with GTK 4 and
# GnomeDesktop 4 (the libgnome-desktop-4 client gsd-power uses).
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
binary=${1:-$here/../../../rust/target/debug/pantheon-compositor}
[[ -x $binary ]] || { echo "build it first: cargo build -p pantheon-compositor (or pass a path)" >&2; exit 2; }
for tool in xvfb-run dbus-run-session xdotool python3; do
  command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 2; }
done
log=$(mktemp)
trap 'rm -f "$log"' EXIT
BIN=$binary PROBE_DIR=$here LOG=$log \
xvfb-run -a -s "-screen 0 1280x800x24" dbus-run-session -- bash -c '
  export HOST_DISPLAY=$DISPLAY
  rt=$(mktemp -d); chmod 700 "$rt"; export XDG_RUNTIME_DIR=$rt
  env -u WAYLAND_DISPLAY "$BIN" --backend nested >"$LOG" 2>&1 &
  comp=$!
  for _ in $(seq 1 60); do sock=$(ls "$rt" | grep "^wayland-[0-9]*$" | head -1 || true); [ -n "$sock" ] && break; sleep 0.25; done
  [ -n "${sock:-}" ] || { echo "compositor socket never appeared"; tail -5 "$LOG"; kill $comp; exit 3; }
  for _ in $(seq 1 40); do gdbus introspect --session --dest org.gnome.Mutter.IdleMonitor --object-path /org/gnome/Mutter/IdleMonitor/Core >/dev/null 2>&1 && break; sleep 0.25; done
  set +e
  env -u DISPLAY WAYLAND_DISPLAY=$sock GDK_BACKEND=wayland GSK_RENDERER=cairo timeout 90 python3 -W ignore "$PROBE_DIR/probe.py"
  status=$?
  kill $comp 2>/dev/null; wait $comp 2>/dev/null
  if [ $status -ne 0 ]; then echo "--- compositor log tail"; grep -iE "idle|power|error|warn" "$LOG" | tail -15; fi
  rm -rf "$rt"; exit $status'
