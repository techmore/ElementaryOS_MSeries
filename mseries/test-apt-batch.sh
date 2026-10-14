#!/usr/bin/env bash
# Exercise batch refresh/invalidation without network, sudo or system changes.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib-apt.sh"
test_directory=$(mktemp -d)
trap 'rm -rf -- "$test_directory"' EXIT
MSERIES_APT_BATCH_DIR=$test_directory
test_digest=initial
test_fail=0
mseries_apt_sources_digest() { printf '%s\n' "$test_digest"; }
sudo() {
  [[ $* == 'apt-get update --error-on=any -qq' ]] || return 99
  printf 'refresh\n' >>"$test_directory/calls"
  if (( test_fail )); then return 42; fi
}
assert_calls() { [[ $(wc -l <"$test_directory/calls") == "$1" ]]; }

mseries_apt_refresh
mseries_apt_refresh
assert_calls 1
test_digest=added-repository
mseries_apt_refresh
assert_calls 2
test_digest=changed-keyring
test_fail=1
if mseries_apt_refresh; then echo 'FAIL failed refresh reported success'; exit 1; fi
assert_calls 3
[[ $(cat "$test_directory/refresh.sha256") == added-repository ]]
test_fail=0
mseries_apt_refresh
assert_calls 4
[[ $(cat "$test_directory/refresh.sha256") == changed-keyring ]]

# Individually invoked installers retain their normal refresh behavior.
unset MSERIES_APT_BATCH_DIR
mseries_apt_refresh
mseries_apt_refresh
assert_calls 6
echo 'APT batch refresh tests passed'
