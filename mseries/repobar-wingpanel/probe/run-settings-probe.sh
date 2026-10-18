#!/bin/bash
# Render RepoBar Settings headlessly (Xvfb + fake HOME + fake helper). Usage: run-settings-probe.sh BUILD_DIR OUT_DIR [light|dark]
set -euo pipefail
build=$(realpath "$1"); out=$2; scheme=${3:-light}
mkdir -p "$out"
home=$(mktemp -d); trap 'rm -rf "$home" 2>/dev/null || true' EXIT
mkdir -p "$home/.local/bin"
cat > "$home/.local/bin/mseries-repobar" <<'HELPER'
#!/bin/sh
case "$1 $2" in
  "settings show") echo '{"host":"github.com","refreshInterval":300,"repoLimit":20,"menuSort":"activity","showForks":false,"showArchived":true,"localRoot":"/home/me/Projects","localDepth":4,"repoStates":{"example/old-tool":"hidden","example/panel-suite":"pinned"}}' ;;
  "auth status") echo '{"host":"github.com","authenticated":true,"account":"example","message":""}' ;;
esac
HELPER
chmod +x "$home/.local/bin/mseries-repobar"
theme=io.elementary.stylesheet.blueberry; [ "$scheme" = dark ] && theme="$theme:dark"
display=:$((90 + RANDOM % 9))
Xvfb "$display" -screen 0 560x760x24 >/dev/null 2>&1 & xvfb=$!
sleep 1
env -i PATH="$PATH" HOME="$home" XDG_DATA_DIRS="$(dirname "$0")/..:/usr/local/share:/usr/share" DISPLAY="$display" LANG=C.UTF-8 \
  GTK_THEME="$theme" GSK_RENDERER=cairo GDK_BACKEND=x11 "$build/mseries-repobar-settings" >/dev/null 2>&1 & app=$!
sleep 4
python3 -W ignore -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay='$display').save('$out/settings-$scheme.png')"
kill "$app" "$xvfb" 2>/dev/null || true
echo "rendered settings ($scheme)"
