#!/usr/bin/env bash
# post-install.sh records and summarises per-stage timing (#47). It runs against a
# throwaway copy of the script with fake stage scripts and a temporary state
# directory: no real installer, no sudo, no network, nothing in $HOME.
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
fails=0
eq() { if [[ $1 == "$2" ]]; then echo "ok   $3"; else echo "FAIL $3: expected [$1], got [$2]" >&2; fails=$((fails + 1)); fi; }
ok() { local d=$1; shift; if "$@"; then echo "ok   $d"; else echo "FAIL $d" >&2; fails=$((fails + 1)); fi; }

if (( EUID == 0 )); then echo "skip: post-install.sh refuses to run as root"; exit 0; fi

tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-post-install-timing.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
repo=$tmp/repo
mkdir -p "$repo/mseries" "$tmp/state"
cp "$here/post-install.sh" "$here/lib-timing.sh" "$here/modrun.py" "$repo/mseries/"
# two stages of the real list, with fake scripts: one succeeds after a short sleep, one fails
printf 'import time\ntime.sleep(0.2)\nprint("settings applied")\n' >"$repo/mseries/apply-desktop-settings.py"
printf '#!/usr/bin/env bash\necho "bridge broke" >&2\nexit 3\n' >"$repo/mseries/install-brightness-bridge.sh"
export XDG_STATE_HOME=$tmp/state HOME=$tmp/home
state=$tmp/state/mseries-post-install

out=$(bash "$repo/mseries/post-install.sh" --dry-run --only settings,brightness)
ok "--dry-run lists the stages" grep -q '\[settings\]' <<<"$out"
ok "--dry-run records no timing" test ! -e "$state/timing.jsonl"

out=$(bash "$repo/mseries/post-install.sh" --only settings,brightness); rc=$?
eq 1 "$rc" "a failed stage still makes the run exit non-zero"
eq 2 "$(grep -c . "$state/timing.jsonl")" "one timing line per stage"
check() { python3 -I - "$state/timing.jsonl" "$@" <<'PY'
import json, sys
rows = {r['name']: r for r in map(json.loads, open(sys.argv[1]))}
name, field, expected = sys.argv[2:5]
assert str(rows[name][field]) == expected, (name, field, rows[name][field], expected)
PY
}
ok "settings is recorded ok" check settings status ok
ok "brightness is recorded failed" bash -c "$(declare -f check); state='$state'; check brightness status failed && check brightness rc 1"
wall=$(python3 -I -c 'import json,sys; print([json.loads(l) for l in open(sys.argv[1]) if "settings" in l][0]["wall_s"])' "$state/timing.jsonl")
ok "the sleeping stage shows its wall time" python3 -I -c 'import sys; sys.exit(0 if float(sys.argv[1]) >= 0.15 else 1)' "$wall"
ok "the table and summary line are printed" grep -qE '^timing: 2 modules ok=1 failed=1 .*mode=serial.*slowest=settings' <<<"$out"
ok "and kept in the log" grep -q '^timing: 2 modules' "$state/last-run.log"
ok "the JSON summary is written" python3 -I -c 'import json,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d["tasks_total"]==2 and d["mode"]=="serial" else 1)' "$state/timing-summary.json"

# without the timing library the stages still run
rm "$repo/mseries/lib-timing.sh"
bash "$repo/mseries/post-install.sh" --only settings >/dev/null; rc=$?
eq 0 "$rc" "no timing library: the stage still runs and succeeds"

(( fails == 0 )) && echo "all tests passed" || { echo "$fails failure(s)" >&2; exit 1; }
