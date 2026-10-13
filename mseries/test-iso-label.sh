#!/usr/bin/env bash
set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/iso-label.sh"

assert_label() {
    local expected=$1 profile=$2 arch=$3 actual
    actual=$(iso_volume_label "$profile" "$arch")
    if [[ "$actual" != "$expected" ]]; then
        printf 'expected %q, got %q\n' "$expected" "$actual" >&2
        exit 1
    fi
    if [[ ! "$actual" =~ ^[A-Z0-9_]{1,32}$ ]]; then
        printf 'invalid ISO volume ID: %q\n' "$actual" >&2
        exit 1
    fi
}

assert_label ELEMENTARY_DAILY_ARM64 daily arm64
assert_label ELEMENTARY_DAILY_PROPOSED_X86_64 daily-proposed x86-64
assert_label ELEMENTARY_ABCDEFGHIJKLMNOPQRSTU abcdefghijklmnopqrstuvwx arm64
