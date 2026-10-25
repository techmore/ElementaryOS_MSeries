#!/bin/bash
# Entirely fake backends/profile: verify all three local counts in the real native widget.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
CB_ASSERT_LOCAL=1 bash "$here/run-probe.sh" "$1" "$out" light opencode-compact

printf '{"showTokens":false}\n' > "$out/preferences.json"
CB_DISPLAY_PREFS="$out/preferences.json" CB_ASSERT_HIDDEN_TOKENS=1 bash "$here/run-probe.sh" "$1" "$out" light opencode-compact

printf '{"showTokens":false,"compactQuota":true}\n' > "$out/preferences.json"
CB_DISPLAY_PREFS="$out/preferences.json" CB_ASSERT_DOTS=1 bash "$here/run-probe.sh" "$1" "$out" light opencode-compact
