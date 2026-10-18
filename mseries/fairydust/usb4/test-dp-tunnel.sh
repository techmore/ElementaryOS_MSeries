#!/usr/bin/env bash
# Read-only dock evidence. No sudo, sysfs writes, force_link or automatic cable instructions.
# Accepts inspect-dock.py options, including --json and saved-log/fake-root inputs.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 -I "$here/inspect-dock.py" "$@"
