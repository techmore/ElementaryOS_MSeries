#!/usr/bin/env bash
# Taskbar clock → Wingpanel datetime indicator popover, under Xvfb.
# Usage: test-calendar.sh [SCREENSHOT_DIR]
# The fallback check always runs. The open/close checks (light and dark) run when the
# datetime indicator is installed; they read the session's real calendars and tasks,
# so pass SCREENSHOT_DIR only on a machine whose data you mean to capture.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
shots=${1:-}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
valac --pkg wingpanel-9 --pkg granite-7 --pkg gmodule-2.0 -d "$work" -o "$work/test-calendar" \
  "$here/TaskbarCalendar.vala" "$here/test-calendar.vala" >"$work/build.log" 2>&1 || { cat "$work/build.log"; exit 1; }
run() { GDK_BACKEND=x11 GSK_RENDERER=cairo xvfb-run -a -s '-screen 0 1280x860x24' "$work/test-calendar" "$@"; }
run missing
indicator=$(pkg-config --variable=indicatorsdir wingpanel-9 2>/dev/null)/libdatetime.so
if [[ ! -e $indicator ]]; then
  echo "SKIP open/close: $indicator is not installed"
  exit 0
fi
for mode in light dark; do
  if [[ -n $shots ]]; then
    mkdir -p "$shots"
    run "$mode" "$shots/calendar-events-$mode.png"
    run "$mode" "$shots/calendar-tasks-$mode.png" tasks
  else
    run "$mode"
  fi
done
