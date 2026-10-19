#!/bin/bash
# Fake backends/profile only: the Grok card, bar segment, details and grok-login launcher in the real widget.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
CB_ASSERT_GROK=1 bash "$here/run-probe.sh" "$1" "$out" light grok
CB_ASSERT_GROK_SIGNIN=1 bash "$here/run-probe.sh" "$1" "$out" dark grok-signin
