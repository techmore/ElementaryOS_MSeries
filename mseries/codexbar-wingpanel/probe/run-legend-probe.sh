#!/bin/bash
# Account legend: with the preference on, each shared sign-in email is named once and the
# cards and bar use its numbered hue; with it off, the cards keep repeating the address.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
CB_ASSERT_LEGEND=off bash "$here/run-probe.sh" "$1" "$out" light shared-accounts
printf '{"accountLegend":true}\n' > "$out/preferences.json"
CB_DISPLAY_PREFS="$out/preferences.json" CB_ASSERT_LEGEND=on bash "$here/run-probe.sh" "$1" "$out" dark shared-accounts
