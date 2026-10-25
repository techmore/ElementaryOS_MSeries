#!/usr/bin/env bash
# Explicit per-user opt-in; no image, browser-policy or session changes.
set -euo pipefail
exec /usr/bin/python3 "$(dirname "$(readlink -f "$0")")/teams-web/setup.py" "$@"
