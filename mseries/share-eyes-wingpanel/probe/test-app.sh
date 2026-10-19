#!/bin/bash
# Headless test of the dock app: stays while a link exists, shows a badge for a waiting viewer, quits after the offer ends.
# Usage: test-app.sh BUILD_DIR SHARE_REPO_CORE_DIR
set -euo pipefail
build=$(realpath "$1"); core=$(realpath "$2")
home=$(mktemp -d); run="$home/run"; mkdir -p "$run"; port=8822
env XDG_RUNTIME_DIR="$run" "$core/scripts/share-demo.sh" --port $port >"$home/demo.out" 2>&1 & demo=$!
cleanup() { kill -TERM "$demo" 2>/dev/null; wait "$demo" 2>/dev/null || true; rm -rf "$home" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 120); do [ -s "$run/rupert-share/state.json" ] && break; sleep 0.5; done
field() { python3 -I -c "import json;print(json.load(open('$run/rupert-share/state.json'))['$1'])"; }
email=$(field email); pass=$(field password); jar="$home/jar"
curl -fs -c "$jar" "http://127.0.0.1:$port/auth/login" -H 'content-type: application/json' -d "{\"email\":\"$email\",\"password\":\"$pass\"}" >/dev/null
api() { curl -fs -b "$jar" -H 'x-rupert-share: 1' -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$port/api/v1/share/$1"; }
link=$(api links); tok=$(echo "$link" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['token'])"); lid=$(echo "$link" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['id'])")
cat >"$home/inner.sh" <<INNER
dbus-monitor "interface='com.canonical.Unity.LauncherEntry'" > "$home/mon.txt" 2>&1 &
mon=\$!
sleep 1
env XDG_RUNTIME_DIR="$run" GSK_RENDERER=cairo "$build/mseries-share-eyes" > "$home/app.out" 2>&1 &
app=\$!
sleep 5
kill -0 \$app 2>/dev/null && echo "app-alive-with-link: yes" || echo "app-alive-with-link: NO"
curl -fs -b "$jar" -H 'x-rupert-share: 1' -H 'content-type: application/json' -d '{}' http://127.0.0.1:$port/api/v1/share/start >/dev/null
curl -fs -X POST -H "authorization: Bearer $tok" http://127.0.0.1:$port/api/v1/share/view/join >/dev/null
sleep 5
grep -c "count" "$home/mon.txt" | sed 's/^/badge-signal-lines: /'
grep -E "int64 [1-9]" "$home/mon.txt" | head -1 | sed 's/^ */badge-count-seen: /'
curl -fs -b "$jar" -H 'x-rupert-share: 1' -X DELETE http://127.0.0.1:$port/api/v1/share/links/$lid >/dev/null
curl -fs -b "$jar" -H 'x-rupert-share: 1' -H 'content-type: application/json' -d '{}' http://127.0.0.1:$port/api/v1/share/stop >/dev/null
for i in \$(seq 1 20); do kill -0 \$app 2>/dev/null || { echo "app-quit-after-offer-ended: yes (\${i}s)"; break; }; sleep 1; done
kill -0 \$app 2>/dev/null && echo "app-quit-after-offer-ended: NO"
kill \$mon 2>/dev/null
INNER
env -i PATH="$PATH" HOME="$home" XDG_RUNTIME_DIR="$run" LANG=C.UTF-8 GDK_BACKEND=x11 xvfb-run -a -s "-screen 0 800x700x24" dbus-run-session -- bash "$home/inner.sh" 2>&1 | grep -v libEGL
cat "$home/app.out" | grep -v -i "egl\|dri3" | head -5
