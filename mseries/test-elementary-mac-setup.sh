#!/usr/bin/env bash
# Unit tests for the pure parts of bin/elementary-mac-setup (state machine,
# validators, config round-trip). Sourcing the script runs nothing.
set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/../bin/elementary-mac-setup"

fails=0
eq() { # eq EXPECTED ACTUAL NAME
  if [[ $1 != "$2" ]]; then echo "FAIL $3: expected '$1', got '$2'" >&2; fails=$((fails + 1)); fi
}
ok()  { "$@" || { echo "FAIL expected success: $*" >&2; fails=$((fails + 1)); }; }
bad() { if "$@"; then echo "FAIL expected failure: $*" >&2; fails=$((fails + 1)); fi; }

# next_step BOOT_SEPARATE ENCRYPTED WANT_ENCRYPT INSTALLED
eq boot-layout  "$(next_step 0 0 1 0)" "fresh, encrypting"
eq encrypt      "$(next_step 1 0 1 0)" "boot moved, encrypting"
eq elementary   "$(next_step 1 1 1 0)" "encrypted"
eq elementary   "$(next_step 0 0 0 0)" "no encryption wanted"
eq done         "$(next_step 1 1 1 1)" "finished"
eq done         "$(next_step 0 0 0 1)" "finished, unencrypted"

ok  valid_username alice
bad valid_username root
bad valid_username 'Bad Name'
ok  valid_hostname elementary-m1
ok  valid_hostname mac.example.org
bad valid_hostname -bad
bad valid_hostname 'has space'

# The config file is sourced as root: hostile values must round-trip inert.
tmp=$(mktemp -d)
CONF=$tmp/conf
want_encrypt=1 username=alice hostname=box keymap=us keep_default=0 \
  password_hash='$6$salt$hash;touch /tmp/pwned' repo='a/b; touch /tmp/pwned' ref=main forge=github.com
save_conf
want_encrypt=0 username="" password_hash=""
load_conf
eq 'a/b; touch /tmp/pwned' "$repo" "repo round-trip"
eq '$6$salt$hash;touch /tmp/pwned' "$password_hash" "hash round-trip"
eq alice "$username" "user round-trip"
[[ ! -e /tmp/pwned ]] || { echo "FAIL config executed its values" >&2; fails=$((fails + 1)); }
eq 600 "$(stat -c %a "$CONF")" "conf mode"
unlink "$CONF"; rmdir "$tmp"

forge=github.com repo=techmore/ElementaryOS_MSeries ref=main
eq https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/bin/elementary-mac-setup \
  "$(raw_url bin/elementary-mac-setup)" "raw url"

# mkinitcpio-snippet: hooks land in Omarchy Mac's proven order, idempotently, and
# the block can be removed again.
snip=$(dirname -- "${BASH_SOURCE[0]}")/boot/mkinitcpio-snippet
mk=$(mktemp)
printf 'HOOKS=(base udev asahi autodetect modconf block encrypt filesystems fsck)\n' >"$mk"
for n in initramfs-console initramfs-splash initramfs-splash; do MKINITCPIO_CONF=$mk bash "$snip" add "$n"; done
eq "base udev asahi plymouth keyboard autodetect modconf kms keymap consolefont block encrypt filesystems fsck" \
  "$(bash -c 'source "$1"; echo "${HOOKS[*]}"' _ "$mk")" "hook order"
eq 1 "$(grep -c '>>> elementary-mac initramfs-splash' "$mk")" "splash block written once"
for n in initramfs-console initramfs-splash; do MKINITCPIO_CONF=$mk bash "$snip" remove "$n"; done
eq "base udev asahi autodetect modconf block encrypt filesystems fsck" \
  "$(bash -c 'source "$1"; echo "${HOOKS[*]}"' _ "$mk")" "hooks after remove"
unlink "$mk"

(( fails == 0 )) && echo "all tests passed" || { echo "$fails failure(s)" >&2; exit 1; }
