#!/usr/bin/env bash
# Reproducible integration fixes from the live journal audit, 2026-10-12.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$repo/mseries/install-brightness-bridge.sh"
if [[ -x "$HOME/.local/bin/signal-desktop" ]]; then
  bash "$repo/mseries/install-signal-integration.sh"
fi
# Ubuntu's vendor unit places StandardError in [Install], where systemd ignores
# it. Correct a user override from the installed source, preserving ExecStart.
/usr/bin/python3 - <<'PY'
from pathlib import Path
source = Path('/usr/lib/systemd/user/spice-vdagent.service')
if source.exists():
    text = source.read_text()
    section = ''
    misplaced = False
    for line in text.splitlines():
        if line.startswith('['): section = line.strip()
        if line.strip() == 'StandardError=null' and section == '[Install]': misplaced = True
    if misplaced:
        target = Path.home() / '.config/systemd/user/spice-vdagent.service'
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and not target.read_text().startswith('# MSeries corrected vendor unit'):
            print('Existing SPICE user override preserved:', target)
        else:
            lines = [line for line in text.splitlines() if line.strip() != 'StandardError=null']
            fixed = '\n'.join(lines).replace('[Service]\n', '[Service]\nStandardError=null\n')
            target.write_text('# MSeries corrected vendor unit; regenerate after package upgrades.\n' + fixed + '\n')
            print('Corrected SPICE stderr directive placement.')
PY
systemctl --user daemon-reload
# A stopped, disabled snap wrapper returned shell exit 143 on intentional stop.
# Clear only that stale state; leave native CUPS and genuine failures alone.
unit=snap.cups.cups-browsed.service
if [[ $(systemctl is-enabled "$unit" 2>/dev/null || true) == disabled &&
      $(systemctl show "$unit" -p ExecMainStatus --value) == 143 &&
      $(systemctl show "$unit" -p ActiveState --value) == failed ]]; then
  sudo systemctl reset-failed "$unit"
fi
