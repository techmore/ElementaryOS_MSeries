#!/usr/bin/env bash
# The PAM helper must change exactly the service asked for, keep a backup, be
# idempotent and refuse bad input. Runs unprivileged against a scratch directory.
set -euo pipefail
helper=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../../aurora-sep" && pwd)/mseries-aurora-touchid-apply-pam
dir=$(mktemp -d); trap 'rm -rf "$dir"' EXIT
export MSERIES_PAM_DIR=$dir
printf 'session required pam_limits.so\n@include common-auth\n' > "$dir/sudo"
fail() { echo "FAIL $*" >&2; exit 1; }
count() { grep -c pam_fprintd "$1" 2>/dev/null || true; }

"$helper" --only sudo >/dev/null
[[ $(count "$dir/sudo") == 1 ]] || fail "sudo should have pam_fprintd"
[[ $(head -1 "$dir/sudo") == *pam_fprintd.so ]] || fail "pam_fprintd must come first"
[[ ! -e $dir/polkit-1 ]] || fail "polkit-1 must be untouched by --only sudo"
"$helper" --only sudo >/dev/null
[[ $(count "$dir/sudo") == 1 ]] || fail "second add must be a no-op"
ls "$dir"/sudo.pre-touchid.* >/dev/null || fail "backup missing"

"$helper" --only polkit-1 >/dev/null
grep -q pam_unix.so "$dir/polkit-1" || fail "polkit-1 needs a full password stack"
"$helper" --only sudo --remove >/dev/null
[[ $(count "$dir/sudo") == 0 ]] || fail "sudo removal"
[[ $(count "$dir/polkit-1") == 1 ]] || fail "--only sudo --remove must keep polkit-1"
grep -q common-auth "$dir/sudo" || fail "removal must keep the password stack"
"$helper" --remove >/dev/null
[[ $(count "$dir/polkit-1") == 0 ]] || fail "--remove clears both"

"$helper" --only bogus >/dev/null 2>&1 && fail "bad service accepted"
unset MSERIES_PAM_DIR
if [[ $EUID -ne 0 ]]; then "$helper" >/dev/null 2>&1 && fail "must refuse non-root without the test hook"; fi
echo "pam helper: ok"
