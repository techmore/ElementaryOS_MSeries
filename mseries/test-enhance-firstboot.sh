#!/usr/bin/env bash
# Tests for enhance-firstboot.sh's run loop (#47): one apt-get for every
# module's build requirements, no automatic retry of a failure that would
# repeat, retry of network trouble, and the per-module fallback when the
# combined install fails. apt-get, ip, curl and systemctl are fakes on PATH;
# nothing is installed and no network is used.
# shellcheck disable=SC1010  # "done" is a state name here, not the keyword
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
fails=0
eq() { # eq EXPECTED ACTUAL DESCRIPTION
  if [[ $1 == "$2" ]]; then echo "ok   $3"; else echo "FAIL $3: expected [$1], got [$2]" >&2; fails=$((fails + 1)); fi
}
ok() { # ok DESCRIPTION COMMAND... (passes when the command succeeds)
  local d=$1; shift
  if "$@"; then echo "ok   $d"; else echo "FAIL $d" >&2; fails=$((fails + 1)); fi
}
has_word() { [[ " $1 " == *" $2 "* ]]; }   # has_word LINE WORD
lacks_word() { ! has_word "$1" "$2"; }
absent() { [[ ! -e $1 ]]; }                 # absent PATH

tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-enhance-firstboot.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
fake=$tmp/bin
mkdir -p "$fake" "$tmp/payload/mseries" "$tmp/payload/shim"
cat >"$fake/apt-get" <<'EOF'
#!/usr/bin/env bash
# Logs every call; `install` fails with apt's wording when it names $FAKE_APT_MISSING.
printf '%s\n' "$*" >>"$FAKE_APT_LOG"
if [[ $1 == install && -n ${FAKE_APT_MISSING:-} && " $* " == *" $FAKE_APT_MISSING "* ]]; then
  echo "E: Unable to locate package $FAKE_APT_MISSING" >&2
  exit 100
fi
EOF
printf '#!/usr/bin/env bash\necho "default via 10.0.0.1 dev eth0"\n' >"$fake/ip"
printf '#!/usr/bin/env bash\nexit 0\n' >"$fake/curl"
printf '#!/usr/bin/env bash\nexit 0\n' >"$fake/systemctl"
chmod +x "$fake"/*
printf 'apple,j314s\0apple,t6000\0' >"$tmp/compatible"
printf '#!/usr/bin/env bash\necho brave installed\n' >"$tmp/payload/mseries/install-brave.sh"
# the scheduler and its module graph ship in the payload next to the install scripts
cp "$here/modrun.py" "$here/lib-timing.sh" "$here/enhance-modules.json" "$tmp/payload/mseries/"
export PATH=$fake:$PATH FAKE_APT_LOG=$tmp/apt.log
export ELEMENTARY_MAC_PAYLOAD=$tmp/payload ELEMENTARY_MAC_COMPATIBLE=$tmp/compatible ELEMENTARY_MAC_FAKE_ROOT=1

run() { # run STATE-DIR [ARGS...] -> runs the first-boot job against that state directory
  local state=$1; shift
  ELEMENTARY_MAC_STATE=$state ELEMENTARY_MAC_LOG=$state/enhance.log bash "$here/enhance-firstboot.sh" "$@"
}
state_of() { run "$1" --status | awk -v m="$2" '$1==m {print $2}'; }
installs() { grep -c '^install ' "$FAKE_APT_LOG"; }
updates() { grep -c '^update' "$FAKE_APT_LOG"; }
video_script() { printf '#!/usr/bin/env bash\n%s\n' "$1" >"$tmp/payload/mseries/install-video-decode.sh"; }

# --- 1. everything succeeds: one combined install, every module settles ----------
state=$tmp/s1; mkdir -p "$state"; : >"$FAKE_APT_LOG"
video_script 'echo video ok'
run "$state" --run >/dev/null
eq 1 "$(installs)" "all build requirements are installed with one apt-get install"
eq 1 "$(updates)" "apt-get update runs once"
line=$(grep '^install ' "$FAKE_APT_LOG")
for p in curl meson libva-dev qml6-module-qtquick; do
  ok "combined install includes $p (brave, video, desktop-user-deps)" has_word "$line" "$p"
done
eq 1 "$(tr ' ' '\n' <<<"$line" | grep -cx curl)" "a package shared by several modules is listed once"
ok "modules whose payload is missing add nothing" lacks_word "$line" libwingpanel-9-dev
eq done "$(state_of "$state" brave)" "brave done"
eq done "$(state_of "$state" video)" "video done"
eq done "$(state_of "$state" desktop-user-deps)" "a dependency-only module is done without its own apt-get"
eq skipped "$(state_of "$state" gestures)" "a module without payload is skipped"
ok "the service retires when every module settled" test -f "$state/finished"
ok "the log says the requirements were installed in one step" grep -q 'in one step (' "$state/enhance.log"

# --- 2. a failure that would repeat is final, not retried three times ------------
state=$tmp/s2; mkdir -p "$state"; : >"$FAKE_APT_LOG"
video_script 'echo "fatal: repository https://example.invalid/x not found" >&2; exit 128'
run "$state" --run >/dev/null
eq done "$(state_of "$state" brave)" "the other modules still run"
eq failed:3 "$(state_of "$state" video)" "a deterministic failure uses up every attempt at once"
eq 'fatal: repository https://example.invalid/x not found' "$(cat "$state/video.reason")" "the reason is recorded"
status=$(run "$state" --status)
ok "--status shows the reason and the fix" grep -q '^video .*not retried: fatal: repository.*--retry video' <<<"$status"
ok "the log explains why it is not retried" \
  grep -q 'video: install failed (exit 128) and would fail the same way again; not retried' "$state/enhance.log"
ok "the service retires instead of wasting two more boots" test -f "$state/finished"
installs_before=$(installs)
run "$state" --run >/dev/null
eq "$installs_before" "$(installs)" "a second run does not rebuild or reinstall anything"
eq failed:3 "$(state_of "$state" video)" "a second run leaves the final failure alone"
# after the fix, --retry forgets the failure and runs the module again at once
video_script 'echo fixed'
run "$state" --retry video >/dev/null
ok "--retry forgets the reason" absent "$state/video.reason"
eq done "$(state_of "$state" video)" "after --retry the fixed module completes"

# --- 3. network trouble is retried on the next boot ----------------------------------
state=$tmp/s3; mkdir -p "$state"; : >"$FAKE_APT_LOG"
video_script 'echo "curl: (6) Could not resolve host: github.com" >&2; exit 1'
run "$state" --run >/dev/null
eq failed:1 "$(state_of "$state" video)" "a network failure counts one attempt"
ok "no final reason for a network failure" absent "$state/video.reason"
ok "the service stays enabled for the next boot" absent "$state/finished"
ok "the log says it will be retried" \
  grep -q 'video: install failed (exit 1), looks like a network problem; attempt 1 of 3' "$state/enhance.log"
run "$state" --run >/dev/null
eq failed:2 "$(state_of "$state" video)" "the next boot tries again"

# --- 4. the combined install fails: fall back per module, blame only the bad one ----
state=$tmp/s4; mkdir -p "$state"; : >"$FAKE_APT_LOG"
video_script 'echo video ok'
FAKE_APT_MISSING=libva-dev run "$state" --run >/dev/null
ok "the log records the fallback" grep -q 'combined install failed; each module installs its own requirements' "$state/enhance.log"
eq done "$(state_of "$state" brave)" "brave installs its own requirements and completes"
eq done "$(state_of "$state" desktop-user-deps)" "desktop-user-deps completes"
eq failed:3 "$(state_of "$state" video)" "the module with the unavailable package fails for good"
eq 'E: Unable to locate package libva-dev' "$(cat "$state/video.reason")" "the missing package is the recorded reason"
eq 5 "$(installs)" "install calls: combined, brave, video twice (around an update), desktop-user-deps"
eq 2 "$(updates)" "apt-get update: once at start, once for the failing module"
ok "the service retires: nothing is left to retry" test -f "$state/finished"

# --- 5. --retry with no module clears every failure -----------------------------------
run "$state" --retry >/dev/null
ok "--retry without a module clears all" absent "$state/video.reason"

# --- 6. every run is timed; the default is serial -------------------------------------
# json_field FILE FIELD [NAME]: a field of the summary document, or of one task's record.
json_field() {
  python3 -I - "$@" <<'PY'
import json, sys
path, field = sys.argv[1], sys.argv[2]
if len(sys.argv) > 3:
    rows = [json.loads(l) for l in open(path) if l.strip()]
    value = next(r for r in rows if r['name'] == sys.argv[3])[field]
else:
    value = json.load(open(path))[field]
print(value)
PY
}
cpu_of() { python3 -I -c 'import json,sys; r=[json.loads(l) for l in open(sys.argv[1]) if l.strip()]; r=[x for x in r if x["name"]==sys.argv[2]][0]; print(round(r["cpu_user_s"]+r["cpu_sys_s"],2))' "$1" "$2"; }
at_least() { python3 -I -c 'import sys; sys.exit(0 if float(sys.argv[1]) >= float(sys.argv[2]) else 1)' "$1" "$2"; }

state=$tmp/s6; mkdir -p "$state"; : >"$FAKE_APT_LOG"
printf '#!/usr/bin/env bash\necho brave installed\nsleep 0.3\n' >"$tmp/payload/mseries/install-brave.sh"
video_script 'python3 -c "
import time
t = time.process_time()
while time.process_time() - t < 0.3: pass"'
run "$state" --run >"$state/stdout"
ok "the default run is serial" bash -c "! grep -q 'with up to [0-9]* at a time' '$state/enhance.log'"
ok "a timing log line per module that ran (the 9 without payload count as not applicable)" test "$(grep -c . "$state/timing.jsonl")" -eq 12
eq ok "$(json_field "$state/timing.jsonl" status brave)" "brave is recorded ok"
ok "brave's wall time covers its 0.3 s" at_least "$(json_field "$state/timing.jsonl" wall_s brave)" 0.25
ok "video's CPU time is recorded (busy for 0.3 s)" at_least "$(cpu_of "$state/timing.jsonl" video)" 0.2
ok "the start precedes the end" at_least "$(json_field "$state/timing.jsonl" end video)" "$(json_field "$state/timing.jsonl" start video)"
eq serial "$(json_field "$state/timing-summary.json" mode)" "the summary is for a serial run"
eq 3 "$(json_field "$state/timing-summary.json" ok)" "the JSON summary counts brave, video and desktop-user-deps as ok"
eq 9 "$(json_field "$state/timing-summary.json" not_applicable)" "and the modules without payload as not applicable"
ok "the log has the human summary line" grep -qE '^timing: 12 modules ok=3 failed=0 skipped=0 n/a=9 wall=[0-9.]+s cpu=[0-9.]+s mode=serial .*slowest=' "$state/enhance.log"
ok "the table lists the slowest module first" bash -c "grep -A1 '^module ' '$state/enhance.log' | tail -1 | grep -qE '^(brave|video) '"
timing=$(run "$state" --timing)
ok "--timing prints the last run" grep -q '^timing: 12 modules' <<<"$timing"
run "$state" --run >/dev/null
ok "a run with nothing left to do keeps the previous timing" test "$(grep -c . "$state/timing.jsonl")" -eq 12

# --- 7. parallel is opt-in, runs independent modules together, and keeps apt holders apart ---
# brave and video each wait for the other to start: they pass only when they really overlap.
rendezvous() { # rendezvous MODULE OTHER
  printf '#!/usr/bin/env bash\ntouch "%s/%s.up"\nfor _ in $(seq 100); do [[ -e "%s/%s.up" ]] && exit 0; sleep 0.05; done\necho "fatal: never ran alongside %s" >&2; exit 1\n' \
    "$tmp" "$1" "$tmp" "$2" "$2"
}
rm -f "$tmp"/*.up
rendezvous brave video >"$tmp/payload/mseries/install-brave.sh"
rendezvous video brave >"$tmp/payload/mseries/install-video-decode.sh"
state=$tmp/s7; mkdir -p "$state"; : >"$FAKE_APT_LOG"
MSERIES_JOBS=4 run "$state" --run --parallel >"$state/stdout"
eq done "$(state_of "$state" brave)" "parallel: brave done (it saw video running)"
eq done "$(state_of "$state" video)" "parallel: video done (it saw brave running)"
eq 1 "$(installs)" "parallel mode still installs the requirements once"
eq 1 "$(updates)" "and updates apt once"
ok "the log says how many ran at once" grep -q 'running [0-9]* modules with up to 4 at a time' "$state/enhance.log"
eq parallel "$(json_field "$state/timing-summary.json" mode)" "the summary is for a parallel run"
ok "at least two modules ran at the same time" at_least "$(json_field "$state/timing-summary.json" peak_concurrency)" 2
ok "each module's log is in the combined log" bash -c "grep -q 'brave: starting' '$state/enhance.log' && grep -q 'video: starting' '$state/enhance.log'"
ok "combined log is in module order, not finish order" bash -c "[[ \$(grep -n 'brave: done' '$state/enhance.log' | cut -d: -f1) -lt \$(grep -n 'video: done' '$state/enhance.log' | cut -d: -f1) ]]"
ok "the service retires" test -f "$state/finished"
ok "per-module scratch logs are removed" absent "$state/logs"

# the same flag through the environment, with apt holders: brave and gestures never overlap
order=$tmp/order; : >"$order"
for pair in "brave install-brave.sh" "gestures install-touchegg.sh"; do
  set -- $pair
  printf '#!/usr/bin/env bash\necho "%s start" >>"%s"\nsleep 0.3\necho "%s end" >>"%s"\n' "$1" "$order" "$1" "$order" >"$tmp/payload/mseries/$2"
done
video_script 'echo video ok'
state=$tmp/s8; mkdir -p "$state"; : >"$FAKE_APT_LOG"
MSERIES_PARALLEL=1 MSERIES_JOBS=4 run "$state" --run >/dev/null
eq done "$(state_of "$state" gestures)" "gestures done in parallel mode"
ok "apt holders run one after the other" bash -c "[[ \$(tr '\n' ' ' <'$order') == 'brave start brave end gestures start gestures end ' || \$(tr '\n' ' ' <'$order') == 'gestures start gestures end brave start brave end ' ]]"

# --- 9. the serial flag and unsafe situations win over --parallel --------------------
state=$tmp/s9; mkdir -p "$state"; : >"$FAKE_APT_LOG"; : >"$order"
MSERIES_SERIAL=1 MSERIES_JOBS=4 run "$state" --run --parallel >/dev/null
ok "MSERIES_SERIAL=1 is reported" grep -q 'parallel mode requested but not used: MSERIES_SERIAL=1' "$state/enhance.log"
eq done "$(state_of "$state" gestures)" "serial fallback still completes every module"
ok "and really ran one at a time" bash -c "grep -q . '$order' && ! grep -q 'with up to [0-9]* at a time' '$state/enhance.log'"

state=$tmp/s10; mkdir -p "$state"; : >"$FAKE_APT_LOG"
FAKE_APT_MISSING=libva-dev MSERIES_JOBS=4 run "$state" --run --parallel >/dev/null
ok "a failed combined install forces serial" grep -q 'not used: the combined requirements install did not complete' "$state/enhance.log"
eq done "$(state_of "$state" brave)" "the fallback path still installs the modules that can be installed"

state=$tmp/s11; mkdir -p "$state"; : >"$FAKE_APT_LOG"
MSERIES_JOBS=1 run "$state" --run --parallel >/dev/null
ok "one worker means serial" grep -q 'not used: only one worker' "$state/enhance.log"

# --- 10. a failing module in parallel mode is recorded and does not stop the rest ----------
state=$tmp/s12; mkdir -p "$state"; : >"$FAKE_APT_LOG"
video_script 'echo "fatal: repository https://example.invalid/x not found" >&2; exit 128'
printf '#!/usr/bin/env bash\necho brave installed\n' >"$tmp/payload/mseries/install-brave.sh"
MSERIES_JOBS=4 run "$state" --run --parallel >/dev/null
eq done "$(state_of "$state" brave)" "parallel: the other module still completes"
eq failed:3 "$(state_of "$state" video)" "parallel: a deterministic failure is final"
eq 'fatal: repository https://example.invalid/x not found' "$(cat "$state/video.reason")" "parallel: the reason is recorded"
eq failed "$(json_field "$state/timing.jsonl" status video)" "parallel: the timing log marks it failed"
eq 1 "$(json_field "$state/timing-summary.json" failed)" "parallel: the summary counts one failure"
ok "parallel: the failure is explained in the combined log" \
  grep -q 'video: install failed (exit 128) and would fail the same way again; not retried' "$state/enhance.log"

# --- 11. timing never gets in the way, and the helpers work on their own ---------------
state=$tmp/s13; mkdir -p "$state"; : >"$FAKE_APT_LOG"
video_script 'echo video ok'
ELEMENTARY_MAC_TIMING_LIB=/nonexistent run "$state" --run >/dev/null
eq done "$(state_of "$state" video)" "without the timing library the modules still install"
ok "and nothing is timed" test ! -s "$state/timing.jsonl"

# shellcheck source=mseries/lib-timing.sh
source "$here/lib-timing.sh"
eq 73200 "$(_timing_clock_ms 1m13.200s)" "a bash 'times' value converts to milliseconds"
eq 1 "$(_timing_clock_ms 0m0.001s)" "a millisecond"
log=$tmp/lib-timing.jsonl; : >"$log"
timing_begin; sleep 0.2; timing_end "$log" slowmod ok 0
timing_begin; timing_end "$log" quickmod failed 1
ok "timing_end writes one JSON line per call" test "$(grep -c . "$log")" -eq 2
ok "the sleep shows as wall time" at_least "$(json_field "$log" wall_s slowmod)" 0.15
eq failed "$(json_field "$log" status quickmod)" "the status is recorded"
summary=$(MODRUN=/nonexistent timing_summary "$log")
ok "without the scheduler a plain list sorted slowest first is printed" \
  grep -Eq '^timing \(slowest first\): slowmod [0-9]+\.[0-9]{1,3}s quickmod [0-9]+\.[0-9]{1,3}s$' <<<"$summary"
summary=$(timing_summary "$log" serial "$tmp/lib-summary.json")
ok "with it, the table and the summary line" grep -q '^timing: 2 modules ok=1 failed=1 .*mode=serial' <<<"$summary"
eq 2 "$(json_field "$tmp/lib-summary.json" tasks_total)" "and the JSON document"

(( fails == 0 )) && echo "all tests passed" || { echo "$fails failure(s)" >&2; exit 1; }
