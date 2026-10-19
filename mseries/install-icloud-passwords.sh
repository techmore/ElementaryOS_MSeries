#!/usr/bin/env bash
# Explicit per-user opt-in. Never called by first-boot enhancement jobs.
set -euo pipefail
exec python3 "$(dirname "$(readlink -f "$0")")/icloud-passwords/setup.py" "$@"
