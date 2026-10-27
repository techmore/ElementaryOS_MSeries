#!/usr/bin/env bash
# mseries_install_indicator must never create a temp file inside the (watched) indicators directory.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
work=$(mktemp -d "${TMPDIR:-/tmp}/mseries-indicator-staging.XXXXXX")
trap 'rm -rf "$work"' EXIT
sudo() { "$@"; }
# shellcheck source=mseries/lib-backup.sh
source "$repo/mseries/lib-backup.sh"

dir="$work/wingpanel-9"; mkdir -p "$dir"
printf old >"$dir/libdatetime.so"; printf new >"$work/built.so"

# Record every name that ever appears in the watched directory.
log="$work/seen"; : >"$log"
( while :; do ls -A "$dir" >>"$log" 2>/dev/null; done ) & watcher=$!
mseries_install_indicator 644 "$work/built.so" "$dir/libdatetime.so"
kill "$watcher" 2>/dev/null || true; wait "$watcher" 2>/dev/null || true

[[ $(cat "$dir/libdatetime.so") == new ]] || { echo "FAIL: module not replaced" >&2; exit 1; }
[[ $(stat -c %a "$dir/libdatetime.so") == 644 ]] || { echo "FAIL: wrong mode" >&2; exit 1; }
if grep -v -x 'libdatetime.so' "$log" | grep -q .; then
  echo "FAIL: extra names appeared in the watched directory:" >&2; grep -v -x 'libdatetime.so' "$log" | sort -u >&2; exit 1
fi
[[ -z $(ls -A "$work/mseries-pending-indicators") ]] || { echo "FAIL: staging file left behind" >&2; exit 1; }

# Install into a directory with no existing module works too.
mseries_install_indicator 755 "$work/built.so" "$dir/libother.so"
[[ -x $dir/libother.so ]] || { echo "FAIL: fresh install" >&2; exit 1; }
echo "ok: indicator staging keeps the watched directory clean"
