#!/usr/bin/env bash
# Tests for mseries/validate.sh: listing, filtering, exit codes and failure
# reporting, using a fixture check list so no real check is run twice.
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
validate=$here/validate.sh
fails=0
tmp=$(mktemp -d "${TMPDIR:-/tmp}/test-validate.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

eq() { # eq EXPECTED ACTUAL DESCRIPTION
  if [[ $1 == "$2" ]]; then echo "ok   $3"; else echo "FAIL $3: expected [$1], got [$2]" >&2; fails=$((fails + 1)); fi
}

fixture=$tmp/checks.sh
cat >"$fixture" <<'EOF'
check alpha 'passes' 'true'
check alpha 'prints and passes' 'echo hello from alpha'
check beta 'fails loudly' 'echo "this is the reason" >&2; exit 3'
check gamma 'needs a tool nobody has' 'shellcheck-not-a-real-tool --version'
EOF
export MSERIES_VALIDATE_CHECKS=$fixture

# --list prints every check and the count, exit 0
out=$(bash "$validate" --list)
eq 0 $? "--list exits 0"
eq 4 "$(grep -c '^[a-z]' <<<"$out" | head -1)" "--list prints one line per check"
eq "4 checks" "$(tail -n1 <<<"$out")" "--list ends with the count"
eq "alpha        passes" "$(head -n1 <<<"$out")" "--list shows group and name"

# --only / --skip filter by group or name
eq "2 checks" "$(bash "$validate" --list --only alpha | tail -n1)" "--only matches a group"
eq "1 checks" "$(bash "$validate" --list --only loudly | tail -n1)" "--only matches part of a name"
eq "3 checks" "$(bash "$validate" --list --skip beta | tail -n1)" "--skip removes a group"
eq "2 checks" "$(bash "$validate" --list --only alpha --only beta --skip prints | tail -n1)" "--only and --skip combine"

# nothing matched: exit 2 and say so
out=$(bash "$validate" --only nothing-matches-this 2>&1)
eq 2 $? "no match exits 2"
eq "no checks matched (see --list)" "$(tail -n1 <<<"$out")" "no match says what to do"

# usage errors
bash "$validate" --bogus >/dev/null 2>&1; eq 2 $? "unknown argument exits 2"
bash "$validate" --only >/dev/null 2>&1; eq 2 $? "--only without a pattern exits 2"
bash "$validate" --help | grep -q 'Run the M-series wiring checks'; eq 0 $? "--help prints the header"

# a clean run exits 0, reports the count, and removes its log directory
out=$(TMPDIR=$tmp bash "$validate" --only alpha 2>&1)
eq 0 $? "passing checks exit 0"
eq "all 2 checks passed" "$(tail -n1 <<<"$out")" "clean run summary"
eq 2 "$(grep -c '^ok ' <<<"$out")" "each passing check prints ok"
eq 0 "$(find "$tmp" -maxdepth 1 -name 'mseries-validate.*' | wc -l)" "clean run removes its logs"

# a failure exits 1, shows the failing command's output, keeps the log, and lists the names
out=$(TMPDIR=$tmp bash "$validate" --only alpha --only beta 2>&1)
eq 1 $? "a failing check exits 1"
grep -q '^FAIL  beta         fails loudly (exit 3' <<<"$out"; eq 0 $? "failure line names the check and exit code"
grep -q 'this is the reason' <<<"$out"; eq 0 $? "failure shows the check output"
grep -q '^1 of 3 checks failed, 2 passed:' <<<"$out"; eq 0 $? "summary counts failed and passed"
grep -q '^  - beta: fails loudly' <<<"$out"; eq 0 $? "summary lists the failed check"
eq 1 "$(find "$tmp" -maxdepth 1 -name 'mseries-validate.*' | wc -l)" "failed run keeps its logs"
rm -rf "$tmp"/mseries-validate.*

# --fail-fast stops after the first failure
out=$(TMPDIR=$tmp bash "$validate" --fail-fast 2>&1)
eq 1 $? "--fail-fast exits 1 on a failure"
grep -q '^1 of 3 checks failed' <<<"$out"; eq 0 $? "--fail-fast stops before the remaining checks"
rm -rf "$tmp"/mseries-validate.*

# --verbose streams the output instead of hiding it
out=$(TMPDIR=$tmp bash "$validate" --verbose --only 'prints and' 2>&1)
grep -q '^hello from alpha' <<<"$out"; eq 0 $? "--verbose streams check output"

# a missing tool is named with an install hint
out=$(TMPDIR=$tmp bash "$validate" --only gamma 2>&1)
eq 1 $? "a check whose tool is missing fails"
grep -q 'not installed (sudo apt install' <<<"$out"; eq 0 $? "missing tool prints an install hint"
rm -rf "$tmp"/mseries-validate.*

# the real list is still complete: every unit-test directory CI relied on is covered
unset MSERIES_VALIDATE_CHECKS
real=$(bash "$validate" --list)
for want in 'test-elementary-mac-setup.sh' 'display-space unit tests' 'codexbar' 'dictation unit tests' \
            'test-build-status.mjs' 'packaging scripts' 'calendar data bundled'; do
  grep -q "$want" <<<"$real"; eq 0 $? "real list has: $want"
done
n=$(tail -n1 <<<"$real" | cut -d' ' -f1)
(( n >= 60 )); eq 0 $? "real list has at least 60 checks (has $n)"

(( fails == 0 )) && echo "all tests passed" || { echo "$fails failure(s)" >&2; exit 1; }
