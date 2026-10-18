#!/bin/bash
# Entirely fake backends/profile: verify all three local counts in the real native widget.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
CB_ASSERT_LOCAL=1 bash "$here/run-probe.sh" "$1" "$out" light opencode-compact
