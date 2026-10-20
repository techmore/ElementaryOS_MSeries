#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0
# Build and exercise only the widget, with synthetic data, a private bus/display
# and a temporary HOME. Requires valac, GTK4/Granite7/json-glib development files,
# python3 with PyGObject, dbus-run-session, xvfb-run and timeout.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/home" "$work/runtime" "$work/config" "$work/data" "$work/cache"
chmod 700 "$work/runtime"
valac --pkg gtk4 --pkg granite-7 --pkg json-glib-1.0 \
  -X '-DGETTEXT_PACKAGE="io.elementary.dock"' \
  --directory="$work" -o "$work/probe" \
  "$here/../TaskbarNotifications.vala" "$here/probe.vala" > "$work/build.log" 2>&1 || {
    cat "$work/build.log"; exit 1;
  }
export HOME="$work/home" XDG_CONFIG_HOME="$work/config" XDG_DATA_HOME="$work/data"
export XDG_CACHE_HOME="$work/cache" XDG_RUNTIME_DIR="$work/runtime"
export GSETTINGS_BACKEND=memory G_DEBUG=fatal-criticals GDK_BACKEND=x11
export GSK_RENDERER=cairo GIO_USE_VFS=local GTK_A11Y=none LC_ALL=C
unset UNAVAILABLE
# An absent service must not cause activation or a fatal GTK/JSON error.
timeout 30s dbus-run-session -- env UNAVAILABLE=1 xvfb-run -a "$work/probe"
# Readiness follows name acquisition, rather than relying on a startup sleep.
timeout 30s dbus-run-session -- bash -euo pipefail -c '
  here=$1
  work=$2
  MSERIES_NOTIFICATION_PRIVATE_FIXTURE=1 python3 "$here/fixture.py" "$work/ready" > "$work/fixture.log" 2>&1 &
  fixture_pid=$!
  trap '\''kill "$fixture_pid" 2>/dev/null || true; wait "$fixture_pid" 2>/dev/null || true'\'' EXIT
  for ((i=0; i<100; i++)); do
    [[ -f "$work/ready" ]] && break
    kill -0 "$fixture_pid"
    sleep 0.05
  done
  test -f "$work/ready"
  xvfb-run -a "$work/probe"
' notifications-probe "$here" "$work" || {
  cat "$work/fixture.log"; exit 1;
}
echo 'PASS isolated notification UI probe; no deployment or live notification data'
