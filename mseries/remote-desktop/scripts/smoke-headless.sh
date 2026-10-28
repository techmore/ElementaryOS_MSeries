#!/usr/bin/env bash
# Whole-system headless smoke test on a PRIVATE session bus: daemon (synthetic
# desktop) + D-Bus owner interface + headless Rust viewer over loopback.
# Never touches the real desktop, the owner's session bus or the display.
#
#   scripts/smoke-headless.sh [path-to-target-dir]
set -euo pipefail

here="$(cd "$(dirname "$0")/.." && pwd)"
target="${1:-${CARGO_TARGET_DIR:-$here/target}}"
host="$target/debug/mseries-remote-hostd"
viewer="$target/debug/tm-remote-viewer"
[ -x "$host" ] && [ -x "$viewer" ] || { echo "build first: cargo build --workspace" >&2; exit 2; }

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
link=""
for _ in $(seq 50); do
    if invite="$("$host" ctl invite 2>/dev/null)"; then
        link="$(printf '%s' "$invite" | python3 -c 'import json,sys; print(json.load(sys.stdin)["links"][0]["url"])')"
        break
    fi
    sleep 0.1
done
[ -n "$link" ] || { echo "no invite link"; cat "$work/host.log"; exit 1; }

"$viewer" --loopback --seconds 4 --wait 20 "$link" >"$work/viewer.json" 2>"$work/viewer.err" &
vpid=$!

req=""
for _ in $(seq 100); do
    req="$("$host" ctl status | python3 -c 'import json,sys; p=json.load(sys.stdin).get("pending"); print(p["id"] if p else "")')"
    [ -n "$req" ] && break
    sleep 0.1
done
[ -n "$req" ] || { echo "viewer never reached the consent prompt"; cat "$work/viewer.err"; exit 1; }
phase="$("$host" ctl status | python3 -c 'import json,sys; print(json.load(sys.stdin)["phase"])')"
[ "$phase" = pending ] || { echo "expected pending before approval, got $phase"; exit 1; }

"$host" ctl approve "$req"
wait "$vpid" || { echo "viewer failed:"; cat "$work/viewer.json" "$work/viewer.err"; exit 1; }
cat "$work/viewer.json"
python3 - "$work/viewer.json" <<'PY'
import json, sys
r = json.load(open(sys.argv[1]))
assert r["ok"], r
assert r["frames"] >= 40, f"too few frames: {r['frames']}"
assert (r["width"], r["height"]) == (640, 360), r
assert r["control"] is False, "approval was view-only"
print("smoke: ok,", r["frames"], "frames in", round(r["seconds"], 1), "s")
PY
"$host" ctl stop
"$host" ctl disable
grep -q consent_granted "$work/audit.jsonl" || { echo "audit log missing consent_granted"; exit 1; }
echo "smoke: audit log ok"
