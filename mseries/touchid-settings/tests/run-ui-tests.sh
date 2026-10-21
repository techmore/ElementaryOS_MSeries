#!/usr/bin/env bash
# Drive the Touch ID page against a fake fprintd and a scratch PAM directory.
#   tests/run-ui-tests.sh BUILD_DIR OUT_DIR
# Everything runs on a private session bus and a virtual X display: no real
# sensor, no real /etc/pam.d, no window on the desktop.
set -euo pipefail
build=$(cd "$1" && pwd); out=$2; mkdir -p "$out"; out=$(cd "$out" && pwd)
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

if [[ -z ${TOUCHID_UI_INNER:-} ]]; then
  export TOUCHID_UI_INNER=1
  exec xvfb-run -a -s '-screen 0 1280x900x24' dbus-run-session -- "$0" "$@"
fi

export GDK_BACKEND=x11 GSK_RENDERER=cairo MSERIES_TOUCHID_TEST=1
export MSERIES_TOUCHID_HELPER="$here/../../aurora-sep/mseries-aurora-touchid-apply-pam"
pass=0; fail=0
check() { if eval "$2"; then echo "PASS $1"; pass=$((pass+1)); else echo "FAIL $1"; fail=$((fail+1)); fi; }

fresh_pam() {
  rm -rf "$out/pam"; mkdir -p "$out/pam"
  printf 'session required pam_limits.so\n@include common-auth\n' > "$out/pam/sudo"
  export MSERIES_TOUCHID_PAM_DIR="$out/pam" MSERIES_PAM_DIR="$out/pam"
}

with_fake() {   # with_fake "fake args" -- command...
  local fake_args=$1; shift
  python3 "$here/fake_fprintd.py" $fake_args 2>"$out/fake.log" & local pid=$!
  for _ in $(seq 50); do gdbus introspect --session -d net.reactivated.Fprint -o /net/reactivated/Fprint/Manager >/dev/null 2>&1 && break; sleep 0.1; done
  "$@" || true
  kill $pid 2>/dev/null; wait $pid 2>/dev/null || true
}

shot() { "$build/mseries-touchid-preview" "$@"; }

export MSERIES_TOUCHID_SEP_NODE=/dev/null

# 1. No enclave device: the unavailable page, not a hang.
fresh_pam
MSERIES_TOUCHID_SEP_NODE=/nonexistent/sep-bio with_fake "" shot --light --screenshot "$out/unavailable-light.png"
check "unavailable page rendered" "[[ -s $out/unavailable-light.png ]]"

# 2. Ready, nothing enrolled: switches locked until a finger exists.
fresh_pam
with_fake "" shot --light --screenshot "$out/empty-light.png"
with_fake "" shot --dark  --screenshot "$out/empty-dark.png"
check "empty page rendered (light+dark)" "[[ -s $out/empty-light.png && -s $out/empty-dark.png ]]"
check "empty state leaves PAM untouched" "! grep -q fprintd $out/pam/sudo"

# 3. Two fingers enrolled.
fresh_pam
with_fake "--fingers right-index-finger,left-thumb" shot --light --screenshot "$out/fingers-light.png"
with_fake "--fingers right-index-finger,left-thumb" shot --dark  --screenshot "$out/fingers-dark.png"
check "fingers page rendered" "[[ -s $out/fingers-light.png && -s $out/fingers-dark.png ]]"

# 4. Flip Terminal Commands on: the helper must write pam_fprintd, only to sudo.
fresh_pam
with_fake "--fingers right-index-finger" shot --light --flip "Terminal Commands" --screenshot "$out/sudo-on-light.png"
check "sudo switch writes pam_fprintd" "grep -q 'auth .*sufficient pam_fprintd.so' $out/pam/sudo"
check "sudo switch keeps the password stack" "grep -q common-auth $out/pam/sudo"
check "polkit untouched by the sudo switch" "[[ ! -e $out/pam/polkit-1 ]]"
check "backup written" "ls $out/pam/sudo.pre-touchid.* >/dev/null 2>&1"

# 5. Add Fingerprint sheet mid-enrolment; the fake streams stages.
fresh_pam
with_fake "--fingers right-index-finger --stages 16 --interval 400" \
  shot --light --dialog-screenshot "$out/enroll-light.png"
with_fake "--fingers right-index-finger --stages 16 --interval 400" \
  shot --dark --dialog-screenshot "$out/enroll-dark.png"
check "enrol sheet rendered" "[[ -s $out/enroll-light.png && -s $out/enroll-dark.png ]]"
check "sheet claimed then enrolled the next free finger" "grep -q 'EnrollStart.*left-index-finger' $out/fake.log"
check "closing the sheet stops enrolment" "grep -q EnrollStop $out/fake.log"
check "closing the sheet releases the sensor" "grep -q Release $out/fake.log"

# 6. fprintd's enroll-duplicate ends the sheet cleanly and leaves the sensor released.
fresh_pam
with_fake "--fingers right-index-finger --stages 16 --interval 300 --duplicate-at 3" \
  shot --light --dialog-screenshot "$out/duplicate-light.png"
check "duplicate sheet rendered" "[[ -s $out/duplicate-light.png ]]"
check "duplicate ends with Release" "grep -q Release $out/fake.log"

echo; echo "$pass passed, $fail failed"; [[ $fail -eq 0 ]]
