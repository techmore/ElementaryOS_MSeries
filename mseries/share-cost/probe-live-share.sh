#!/usr/bin/env bash
# Isolated, loopback-only smoke for collect-share-cost.sh against a REAL share
# server: private HOME, private XDG_RUNTIME_DIR, loopback port, one viewer joining
# through the API, no browser and no LAN/public exposure. The live desktop's eyes
# panel watches the real XDG_RUNTIME_DIR and sees none of this.
#
#   bash mseries/share-cost/probe-live-share.sh /path/to/rupert-share/core
#
# Proves the collector's share-state path end to end: the launcher's state.json
# is read, --require-live passes, the viewer count is recorded, and the server
# role matches the rupert-core binary (not the launcher shell). It does NOT
# measure sharing cost: no browser capture runs, so the browser rows are an idle
# browser, not a sharing one.
set -euo pipefail

[[ $# -eq 1 ]] || { echo "Usage: $0 /path/to/rupert-share/core" >&2; exit 2; }
core=$(realpath "$1")
[[ -x $core/scripts/share-demo.sh ]] || { echo "no share-demo.sh in $core" >&2; exit 2; }
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

smoke=$(mktemp -d /tmp/share-cost-probe.XXXXXX)
mkdir -p "$smoke/run" "$smoke/home"
port=8799
if ss -ltn 2>/dev/null | awk '{print $4}' | grep -qE "[:.]$port\$"; then
  echo "port $port is in use; stop the other share first" >&2
  rm -rf "$smoke"; exit 1
fi

cleanup() {
  [[ -n ${demo:-} ]] && kill -TERM "$demo" 2>/dev/null || true
  [[ -n ${demo:-} ]] && wait "$demo" 2>/dev/null || true
  rm -rf "$smoke"
}
trap cleanup EXIT

env -i PATH="$PATH" HOME="$smoke/home" XDG_RUNTIME_DIR="$smoke/run" \
  "$core/scripts/share-demo.sh" --port "$port" >"$smoke/demo.out" 2>&1 &
demo=$!

state="$smoke/run/rupert-share/state.json"
for _ in $(seq 1 240); do [ -s "$state" ] && break; sleep 0.5; done
[ -s "$state" ] || { echo "PROBE FAIL: no state.json"; tail -5 "$smoke/demo.out"; exit 1; }
field() { python3 -I -c "import json;print(json.load(open('$state'))['$1'])"; }
echo "server up: port=$(field port) live=$(field live) viewers=$(field viewers)"

jar="$smoke/jar"
email=$(field email); pass=$(field password)
curl -fs -c "$jar" "http://127.0.0.1:$port/auth/login" -H 'content-type: application/json' \
  -d "{\"email\":\"$email\",\"password\":\"$pass\"}" >/dev/null
api() { curl -fs -b "$jar" -H 'x-rupert-share: 1' -H 'content-type: application/json' -d '{}' "http://127.0.0.1:$port/api/v1/share/$1"; }

api start >/dev/null                       # owner marks the share live
link=$(api links)
tok=$(echo "$link" | python3 -I -c "import json,sys;print(json.load(sys.stdin)['token'])")
curl -fs -X POST -H "authorization: Bearer $tok" "http://127.0.0.1:$port/api/v1/share/view/join" >/dev/null
for _ in $(seq 1 40); do [ "$(field viewers)" = "1" ] && break; sleep 0.5; done
echo "after viewer join: live=$(field live) viewers=$(field viewers)"

# The collector under test, pointed at the isolated runtime dir.
env -i PATH="$PATH" HOME="$smoke/home" XDG_RUNTIME_DIR="$smoke/run" \
  bash "$here/collect-share-cost.sh" 15 probe 1 5 --require-live \
  >"$smoke/capture.csv" 2>"$smoke/collect.err"
cat "$smoke/collect.err" >&2
echo "--- roles and share state seen ---"
grep -v '^#' "$smoke/capture.csv" | awk -F, '{print $6, $7, $8, $16, $17}' | sort -u
echo "--- reduced ---"
python3 "$here/summarize-share-cost.py" "$smoke/capture.csv"

api stop >/dev/null || true
echo "PROBE DONE"
