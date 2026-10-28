#!/usr/bin/env bash
# Headless-Chrome phone test on a PRIVATE session bus (no window on the owner's
# screen). Needs: dbus-run-session, node, playwright-core on NODE_PATH, and a
# Chrome that can decode H.264 (CHROME=/usr/bin/google-chrome by default).
#
#   NODE_PATH=/path/to/node_modules scripts/smoke-browser.sh [target-dir]
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
target="${1:-${CARGO_TARGET_DIR:-$here/target}}"
host="$target/debug/mseries-remote-hostd"
[ -x "$host" ] || { echo "build first: cargo build --workspace" >&2; exit 2; }

if [ -z "${_SMOKE_INNER:-}" ]; then
    exec env _SMOKE_INNER=1 dbus-run-session -- "$0" "$target"
fi

work="$(mktemp -d)"
trap 'kill $(jobs -p) 2>/dev/null || true; rm -rf "$work"' EXIT
cat >"$work/cfg.toml" <<TOML
backend = "test"
listen = "127.0.0.1:0"
advertise = ["127.0.0.1"]
audit_log = "$work/audit.jsonl"
TOML

"$host" --config "$work/cfg.toml" >"$work/host.log" 2>&1 &
for _ in $(seq 50); do "$host" ctl status >/dev/null 2>&1 && break; sleep 0.1; done
"$host" ctl enable

pending() { "$host" ctl status | python3 -c 'import json,sys; p=json.load(sys.stdin).get("pending"); print(p["id"] if p else "")'; }
field() { python3 -c "import json,sys; print(json.load(sys.stdin)$1)"; }

run_phone() { # mode, invite-args...
    local mode="$1"; shift
    local link
    for _ in $(seq 50); do
        link="$("$host" ctl invite "$@" 2>/dev/null | field '["links"][0]["url"]')" && break
        sleep 0.1
    done
    node "$here/tests/browser/phone.mjs" "$link" "$mode" >"$work/phone-$mode.json" 2>"$work/phone-$mode.err" &
    local pid=$!
    local req=""
    for _ in $(seq 200); do req="$(pending)"; [ -n "$req" ] && break; sleep 0.1; done
    [ -n "$req" ] || { echo "phone never asked for consent"; cat "$work/phone-$mode.err"; exit 1; }
    if [ "$mode" = control ]; then "$host" ctl approve "$req" --control; else "$host" ctl approve "$req"; fi
    wait "$pid" || { echo "phone test ($mode) failed:"; cat "$work/phone-$mode.json" "$work/phone-$mode.err"; exit 1; }
    cat "$work/phone-$mode.json"
}

run_phone pair
python3 - "$work/phone-pair.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert r["hashCleared"], "invite stayed in the address bar"
assert r["sawWaitScreen"], "no waiting-for-approval screen"
assert r["size"] == [640, 360], r["size"]
assert r["advancing"], f"video counter not advancing: {r['counters']}"
assert r["chip"] == "View only", r["chip"]
assert r["viewOnlyToast"], "tap in view-only was not explained"
assert not r["errors"], r["errors"]
print("browser pair: ok", r["counters"])
PY
"$host" ctl stop
sleep 0.5

run_phone control --control
python3 - "$work/phone-control.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert r["advancing"] and r["chipAfter"] == "Controlling", r
assert not r["errors"], r["errors"]
print("browser control: ok")
PY
for want in 'Click { button: Left }' 'Move {' 'Click { button: Right }' 'Text { text: "hi" }' 'Key { key: "Escape"'; do
    grep -q "test-backend input: .*$want" "$work/host.log" || { echo "host never received: $want"; cat "$work/host.log"; exit 1; }
done
echo "browser input reached the host: ok"
