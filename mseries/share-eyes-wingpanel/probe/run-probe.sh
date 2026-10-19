#!/bin/bash
# Render the eyes + popover headlessly against a REAL throwaway share server (Xvfb + cairo + private runtime dir/icons).
# Usage: run-probe.sh BUILD_DIR OUT_DIR SHARE_REPO_CORE_DIR
set -euo pipefail
build=$(realpath "$1"); out=$2; core=$(realpath "$3"); here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$out"; home=$(mktemp -d); run="$home/run"; mkdir -p "$run" "$home/share/icons/hicolor/scalable/apps"
cp "$here/icons/eyes.svg" "$home/share/icons/hicolor/scalable/apps/mseries-share-eyes-symbolic.svg"
port=8821
env XDG_RUNTIME_DIR="$run" "$core/scripts/share-demo.sh" --port $port >"$home/demo.out" 2>&1 &
demo=$!
cleanup() { kill -TERM "$demo" 2>/dev/null; wait "$demo" 2>/dev/null || true; rm -rf "$home" 2>/dev/null || true; }
trap cleanup EXIT
for _ in $(seq 1 120); do [ -s "$run/rupert-share/state.json" ] && break; sleep 0.5; done
probe() { env -i PATH="$PATH" HOME="$home" XDG_RUNTIME_DIR="$run" XDG_DATA_DIRS="$home/share:/usr/share" LANG=C.UTF-8 \
    GTK_THEME=io.elementary.stylesheet.blueberry GSK_RENDERER=cairo GDK_BACKEND=x11 \
    xvfb-run -a -s "-screen 0 500x700x24" "$build/render-probe" "$out/$1.png"; }
probe idle
# a viewer link and a pending watcher through the same API the popover uses
email=$(python3 -I -c "import json,sys;print(json.load(open('$run/rupert-share/state.json'))['email'])")
pass=$(python3 -I -c "import json,sys;print(json.load(open('$run/rupert-share/state.json'))['password'])")
jar="$home/jar"; curl -fs -c "$jar" "http://127.0.0.1:$port/auth/login" -H 'content-type: application/json' -d "{\"email\":\"$email\",\"password\":\"$pass\"}" >/dev/null
tok=$(curl -fs -b "$jar" -H 'x-rupert-share: 1' -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$port/api/v1/share/links" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['token'])")
probe with-link
# go live with a waiting viewer, then admit it (the same calls the popover and owner page make)
api() { curl -fs -b "$jar" -H 'x-rupert-share: 1' -H 'content-type: application/json' -d "${3:-{\}}" "http://127.0.0.1:$port/api/v1/share/$2"; }
api x start >/dev/null
vid=$(curl -fs -H "authorization: Bearer $tok" -X POST "http://127.0.0.1:$port/api/v1/share/view/join" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['vid'])")
probe waiting
api x "viewers/$vid/admit" >/dev/null
probe watching
