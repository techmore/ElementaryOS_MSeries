#!/usr/bin/env bash
# Does a toolkit's present() raise a window in the Rust compositor?
#
# Runs pantheon-compositor nested inside a virtual X display with a private
# runtime directory and D-Bus session, so it never touches the live desktop.
# Client A has no recent input and calls present() while a different client B
# has focus. Four scenarios cover both policies, idle and while typing.
#
#   bash run.sh [path/to/pantheon-compositor]     (ONLY=popup runs one scenario,
#                                                KEEP_LOG=<dir> keeps compositor logs)
#
# Needs: xvfb-run, dbus-run-session, xdotool, python3-gi (GTK 4 and GTK 3), Xwayland.
# Expected: strict never raises; raise raises at once when idle and only after
# the user stops typing otherwise, with every keystroke reaching client B.
# focus-probe.py adds: an open menu (xdg_popup grab) closes and gives up the
# keyboard when the compositor focuses another window (D1/D8); an X11
# notification card neither deactivates nor steals the keyboard from the focused
# app; the BadWindow count from short-lived cards is reported, not gated (D2); a refused activation
# and X11 urgency mark the window demands-attention until it is focused (D3).
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
binary=${1:-$here/../../../rust/target/debug/pantheon-compositor}
[[ -x $binary ]] || { echo "build it first: cargo build -p pantheon-compositor (or pass a path)" >&2; exit 2; }
for tool in xvfb-run dbus-run-session xdotool python3; do
  command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 2; }
done
scenario() {
  local mode=$1 policy=$2 log probe=probe.py
  [[ $mode == idle || $mode == typing ]] || probe=focus-probe.py
  log=$(mktemp)
  PROBE=$probe MODE=$mode POLICY=$policy BIN=$binary PROBE_DIR=$here LOG=$log \
  xvfb-run -a -s "-screen 0 1280x800x24" dbus-run-session -- bash -c '
    export HOST_DISPLAY=$DISPLAY
    rt=$(mktemp -d); chmod 700 "$rt"; export XDG_RUNTIME_DIR=$rt
    env -u WAYLAND_DISPLAY RUST_LOG=${RUST_LOG:-info} PANTHEON_ACTIVATION_POLICY=$POLICY "$BIN" --backend nested >"$LOG" 2>&1 &
    comp=$!; export COMP_PID=$comp
    for _ in $(seq 1 60); do sock=$(ls "$rt" | grep "^wayland-[0-9]*$" | head -1 || true); [ -n "$sock" ] && break; sleep 0.25; done
    [ -n "${sock:-}" ] || { echo "compositor socket never appeared"; tail -5 "$LOG"; kill $comp; exit 3; }
    sleep 1
    env -u DISPLAY WAYLAND_DISPLAY=$sock GDK_BACKEND=wayland GSK_RENDERER=cairo timeout 60 python3 -W ignore "$PROBE_DIR/$PROBE" "$MODE" 2>&1 | grep -E "^RESULT" || echo "RESULT no output"
    kill $comp 2>/dev/null || true; wait $comp 2>/dev/null || true; rm -rf "$rt"'
  [[ -n ${KEEP_LOG:-} ]] && cp "$log" "$KEEP_LOG/$mode-$policy.log"
  rm -f "$log"
}
status=0
check() { # mode policy expected-regex; ONLY=<mode> runs one scenario
  [[ -z ${ONLY:-} || $1 == "$ONLY" ]] || return 0
  printf '%-7s %-7s ' "$1" "$2"
  local out; out=$(scenario "$1" "$2" 2>&1 | grep -E '^RESULT' | tail -1 || true); echo "${out:-RESULT none}"
  [[ $out =~ $3 ]] || { echo "  ^ UNEXPECTED (wanted /$3/)"; status=1; }
}
check idle   strict 'never raised'
check idle   raise  'focused=A after [0-9]{1,3} ms'
check typing strict 'never raised'
check typing raise  'focused=A after [0-9]{4,} ms.*typing already finished'
check popup  raise  "keys reached A='xyz' menu entry='' menu closed=True A active=True"
check orcard raise  "A kept focus='abc' A active before=True after=True card clicked=True"
check attention strict "marked=True after [0-9]+ ms cleared=True \| x11 urgent marked=True cleared=True"
exit $status
