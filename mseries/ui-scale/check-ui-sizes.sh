#!/usr/bin/env bash
# Fail on hard-coded UI sizes that should come from the M-Series size system (#332).
# Usage: check-ui-sizes.sh [--list] [--strict]   (see check_ui_sizes.py)
set -euo pipefail
exec python3 -B "$(dirname -- "${BASH_SOURCE[0]}")/check_ui_sizes.py" "$@"
