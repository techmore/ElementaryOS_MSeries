#!/usr/bin/env bash
# Install the narrowly scoped Polkit authorization needed by the DNS monitor.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
install -Dm644 "$repo/mseries/netspeed/netusage/49-mseries-netusage.rules" \
  /etc/polkit-1/rules.d/49-mseries-netusage.rules
echo 'Installed read-only systemd-resolved DNS monitor authorization.'
