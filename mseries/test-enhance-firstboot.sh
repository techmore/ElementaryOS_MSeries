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

(( fails == 0 )) && echo "all tests passed" || { echo "$fails failure(s)" >&2; exit 1; }
