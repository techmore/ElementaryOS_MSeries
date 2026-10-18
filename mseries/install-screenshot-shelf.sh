#!/usr/bin/env bash
# Install the screenshot thumbnail shelf and the Markup launcher for the current user.
#   bash mseries/install-screenshot-shelf.sh              # install and start
#   bash mseries/install-screenshot-shelf.sh --uninstall  # remove
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/screenshot-shelf" && pwd)
bin=$HOME/.local/bin libexec=$HOME/.local/libexec apps=$HOME/.local/share/applications auto=$HOME/.config/autostart
if [[ ${1:-} == --uninstall ]]; then
  pkill -f "$libexec/mseries-screenshot-shelf" 2>/dev/null || true
  rm -f "$libexec/mseries-screenshot-shelf" "$bin/mseries-markup" "$apps/mseries-markup.desktop" "$auto/mseries-screenshot-shelf.desktop"
  echo "Removed the shelf and Markup."; exit 0
fi
command -v swappy >/dev/null || sudo apt-get install -y swappy
mkdir -p "$bin" "$libexec" "$apps" "$auto"
install -m 755 "$here/mseries-screenshot-shelf" "$libexec/mseries-screenshot-shelf"
install -m 755 "$here/mseries-markup" "$bin/mseries-markup"
# Desktop Exec does not expand %h or shell variables. Render absolute, quoted paths.
python3 - "$here" "$apps" "$auto" "$bin" "$libexec" <<'DESKTOP'
from pathlib import Path
import sys
source, apps, auto, bin_dir, libexec = map(Path, sys.argv[1:])
def quoted(path):
    text = str(path).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$')
    return '"' + text.replace('%', '%%') + '"'
for name, target, command in (
    ('mseries-markup.desktop', apps, quoted(bin_dir / 'mseries-markup') + ' %f'),
    ('mseries-screenshot-shelf.desktop', auto, quoted(libexec / 'mseries-screenshot-shelf')),
):
    lines = (source / name).read_text().splitlines()
    (target / name).write_text('\n'.join('Exec=' + command if line.startswith('Exec=') else line for line in lines) + '\n')
DESKTOP
update-desktop-database "$apps" 2>/dev/null || true
pkill -f "$libexec/mseries-screenshot-shelf" 2>/dev/null || true
setsid nohup "$libexec/mseries-screenshot-shelf" >/dev/null 2>&1 &
echo "Screenshot shelf running. Log: ~/.cache/mseries-screenshot-shelf.log"
