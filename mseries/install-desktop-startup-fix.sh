#!/usr/bin/env bash
# Repair full-height saved layouts and stop awaiting a deliberately disabled dock.
# Panel rebuild is separate: install-wingpanel-codexbar-left.sh includes the sizing fix.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $EUID != 0 ]] || { echo 'Run as the desktop user.' >&2; exit 2; }
config=${XDG_CONFIG_HOME:-$HOME/.config}
state=${XDG_STATE_HOME:-$HOME/.local/state}/mseries-desktop-startup/$(date +%Y%m%d-%H%M%S)-$$
helper=$HOME/.local/lib/mseries/display-startup/repair_full_height_layout.py
unit=$config/systemd/user/io.elementary.gala@wayland.service.d/20-full-height-layout.conf
shell=$config/io.elementary.desktop.wm.shell
mkdir -p "$state" "$(dirname "$helper")" "$(dirname "$unit")"
# Record each replaced path, including absence, for an exact private rollback.
for file in "$helper" "$unit" "$shell" "$config/monitors.xml" "$config/mseries/display-profiles.json"; do
    printf '%s\n' "$file" >> "$state/paths"
    if [[ -f $file ]]; then cp -a "$file" "$state/$(basename "$file")"; fi
done
install -m 0755 "$repo/mseries/display-space/repair_full_height_layout.py" "$helper"
# Use explicit quoted paths, retaining non-default XDG config locations.
python3 - "$unit" "$helper" "$config" <<'PY'
from pathlib import Path
import sys
unit, helper, config = sys.argv[1:]
def quote(value):
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'
command = ['/usr/bin/python3', helper, '--check-running-panel', '--profiles',
           config + '/mseries/display-profiles.json', '--monitors', config + '/monitors.xml']
Path(unit).write_text('# M-series: repair stale cropped modes before Gala reads its monitor store.\n'
                     '# Failure is nonfatal; this must never block desktop startup.\n[Service]\n'
                     'ExecStartPre=-' + ' '.join(quote(a) for a in command) + '\n')
PY
if [[ -e $config/mseries/dock/user-disabled ]]; then
    source=$shell
    [[ -f $source ]] || source=/etc/xdg/io.elementary.desktop.wm.shell
    python3 "$repo/mseries/display-space/session_startup.py" --source "$source" --output "$shell" \
        --disabled-marker "$config/mseries/dock/user-disabled"
fi
python3 "$helper" --check-running-panel --profiles "$config/mseries/display-profiles.json" --monitors "$config/monitors.xml"
systemctl --user daemon-reload
echo "Saved private rollback files and path list in $state"
echo 'Startup configuration repaired. The session wait and pre-start hook take effect next sign-in.'
