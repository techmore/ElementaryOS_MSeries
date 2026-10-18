#!/bin/bash
# Render the native Settings window headlessly (Xvfb + fake HOME + fake app/CLI).
# Usage: run-settings-probe.sh BUILD_DIR OUT_DIR [light|dark] [page...]
set -euo pipefail
build=$(realpath "$1"); out=$2; scheme=${3:-light}; shift 3 || shift $#
mkdir -p "$out"
home=$(mktemp -d); run=/run/user/$(id -u)/cbsettings; mkdir -p -m 700 "$run"
trap 'rm -rf "$home" "$run" 2>/dev/null || true' EXIT
mkdir -p "$home/.local/bin" "$home/.config/codexbar"
printf '#!/bin/sh\n[ "$1" = --autostart ] && echo "{\\"enabled\\":true}"\nexit 0\n' > "$home/.local/bin/codexbar-linux"
cat > "$home/.local/bin/codexbar" <<'PY'
#!/usr/bin/env python3
import json
names = {"codex": "Codex", "claude": "Claude", "opencodego": "OpenCode Go", "cursor": "Cursor", "gemini": "Gemini", "copilot": "GitHub Copilot"}
print(json.dumps([{"provider": k, "displayName": v, "enabled": k == "codex", "defaultEnabled": k == "codex"} for k, v in names.items()]))
PY
chmod +x "$home/.local/bin/codexbar-linux" "$home/.local/bin/codexbar"
printf '{"provider":"custom","providerOrder":["codex","claude","opencodego"],"refreshSeconds":300,"notifications":true}\n' > "$home/.config/codexbar/linux.json"
theme=io.elementary.stylesheet.blueberry; [ "$scheme" = dark ] && theme="$theme:dark"
pages=("$@"); [ ${#pages[@]} -gt 0 ] || pages=(general display providers)
for page in "${pages[@]}"; do
  Xvfb :96 -screen 0 700x800x24 >/dev/null 2>&1 & xvfb=$!
  sleep 1
  env -i PATH="$PATH" HOME="$home" XDG_RUNTIME_DIR="$run" XDG_DATA_DIRS=/usr/local/share:/usr/share DISPLAY=:96 LANG=C.UTF-8 \
    GTK_THEME="$theme" GSK_RENDERER=cairo GDK_BACKEND=x11 CODEXBAR_SETTINGS_PAGE="$page" "$build/codexbar-settings" >/dev/null 2>&1 &
  app=$!
  sleep 4
  python3 -W ignore -c "
from PIL import ImageGrab
ImageGrab.grab(xdisplay=':96').save('$out/settings-$page-$scheme.png')"
  kill $app $xvfb 2>/dev/null || true; wait 2>/dev/null || true
  echo "rendered $page ($scheme)"
done
