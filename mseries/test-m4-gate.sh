#!/bin/bash
# Checks the pure helpers in bin/elementary-mac-setup: the SSH key validator and
# the M4 model gate. Sourcing the script runs nothing.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# shellcheck source=/dev/null
. "$ROOT/bin/elementary-mac-setup"

ok() { valid_ssh_key "$1" || { echo "should accept: $1"; exit 1; }; }
bad() { valid_ssh_key "$1" && { echo "should reject: $1"; exit 1; } || true; }
ok "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA me@host"
bad "hunter2"
bad "ssh-ed25519 AAAA; rm -rf /"

dt=$(mktemp)
trap 'rm -f "$dt"' EXIT
DT_COMPATIBLE=$dt
printf 'apple,j773g\0apple,t8132\0apple,arm-platform\0' >"$dt"
is_m4_family || { echo "J773g should be M4"; exit 1; }
[[ $(apple_model) == apple,j773g ]] || { echo "model should be apple,j773g"; exit 1; }
printf 'APPLE,J773G\0' >"$dt"
is_m4_family || { echo "match must fold case"; exit 1; }
printf 'apple,j314s\0apple,t6000\0apple,arm-platform\0' >"$dt"
! is_m4_family || { echo "J314s (M1 Pro) must not be M4"; exit 1; }
printf 'apple,j773gx\0' >"$dt"
! is_m4_family || { echo "match must be whole-string, not a prefix"; exit 1; }
ELEMENTARY_HOST=fedora is_fedora_host || { echo "ELEMENTARY_HOST=fedora must select the Fedora lane"; exit 1; }
! ELEMENTARY_HOST=arch is_fedora_host || { echo "ELEMENTARY_HOST=arch must not select the Fedora lane"; exit 1; }
echo "ok: m4 gate and ssh key validation"
