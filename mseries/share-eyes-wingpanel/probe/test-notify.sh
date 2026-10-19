#!/bin/bash
# Headless: a waiting viewer makes the Quick Settings panel send one desktop notification (captured on a private session bus).
# Usage: test-notify.sh BUILD_DIR SHARE_REPO_CORE_DIR
set -euo pipefail
build=$(realpath "$1"); core=$(realpath "$2")
home=$(mktemp -d); run="$home/run"; mkdir -p "$run"; port=8823
env XDG_RUNTIME_DIR="$run" "$core/scripts/share-demo.sh" --port $port >"$home/demo.out" 2>&1 & demo=$!
trap 'kill -TERM "$demo" 2>/dev/null; wait "$demo" 2>/dev/null || true; rm -rf "$home" 2>/dev/null || true' EXIT
for _ in $(seq 1 120); do [ -s "$run/rupert-share/state.json" ] && break; sleep 0.5; done
field() { python3 -I -c "import json;print(json.load(open('$run/rupert-share/state.json'))['$1'])"; }
jar="$home/jar"; curl -fs -c "$jar" "http://127.0.0.1:$port/auth/login" -H 'content-type: application/json' -d "{\"email\":\"$(field email)\",\"password\":\"$(field password)\"}" >/dev/null
api() { curl -fs -b "$jar" -H 'x-rupert-share: 1' -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$port/api/v1/share/$1"; }
tok=$(api links | python3 -I -c "import json,sys;print(json.load(sys.stdin)['token'])"); api start >/dev/null
cat >"$home/inner.sh" <<INNER
dbus-monitor "interface='org.freedesktop.Notifications'" > "$home/mon.txt" 2>&1 &
mon=\$!
sleep 1
env XDG_RUNTIME_DIR="$run" SHARE_NOTIFY=1 PROBE_MS=14000 GSK_RENDERER=cairo "$build/render-probe" "$home/x.png" > "$home/probe.out" 2>&1 &
sleep 4
echo "before waiting viewer: \$(grep -c 'member=Notify' "$home/mon.txt") notifications"
curl -fs -X POST -H "authorization: Bearer $tok" http://127.0.0.1:$port/api/v1/share/view/join >/dev/null
sleep 5
echo "after waiting viewer: \$(grep -c 'member=Notify' "$home/mon.txt") notifications"
grep -m1 'Someone wants to watch' "$home/mon.txt" | sed 's/^ */text: /'
grep -v -i "egl\|dri3" "$home/probe.out" | head -5; kill \$mon 2>/dev/null
INNER
env -i PATH="$PATH" HOME="$home" XDG_RUNTIME_DIR="$run" LANG=C.UTF-8 GDK_BACKEND=x11 xvfb-run -a -s "-screen 0 800x700x24" dbus-run-session -- bash "$home/inner.sh" 2>&1 
