#!/bin/bash
# Install CodexBar's custom port without interrupting the menu bar. Helpers take effect on their next invocation;
# Wingpanel loads a replaced module at next login. Use --restart only for an intentional panel reload.
#   bash mseries/deploy-codexbar.sh [--restart|--no-restart]
set -euo pipefail
restart=false
case ${1:-} in
  ''|--no-restart) ;;
  --restart) restart=true ;;
  *) echo 'Usage: deploy-codexbar.sh [--restart|--no-restart]' >&2; exit 2 ;;
esac
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
lib="$HOME/.local/lib/codexbar-cli"
mkdir -p "$lib"
for helper in codexbar_claude_history.py codexbar_cache.py codexbar-opencode-local.py codexbar-sessions.py codexbar-accounts.py codexbar-claude.py codexbar-opencode-login.py; do
  install -m 0755 "$repo/mseries/$helper" "$lib/$helper"
done
install -m 0755 "$repo/mseries/codexbar-opencode-wrapper.py" "$HOME/.local/bin/codexbar.new"
mv -f "$HOME/.local/bin/codexbar.new" "$HOME/.local/bin/codexbar"

build=$(mktemp -d "${TMPDIR:-/tmp}/codexbar-deploy.XXXXXX")
trap 'rm -rf "$build"' EXIT
meson setup "$build" "$repo/mseries/codexbar-wingpanel" --prefix=/usr >/dev/null
ninja -C "$build" >/dev/null
meson test -C "$build" --print-errorlogs
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
# install(1) replaces the file instead of overwriting it, so the loaded module is never truncated in place.
sudo install -m 0755 "$build/libcodexbar.so" "$indicators_dir/libcodexbar.so"
for mark in openai claude opencode; do
  sudo install -m 0644 "$repo/mseries/codexbar-wingpanel/icons/$mark.svg" \
    "/usr/share/icons/hicolor/scalable/apps/mseries-codexbar-$mark-symbolic.svg"
done
command -v gtk-update-icon-cache >/dev/null && sudo gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null
install -m 0755 "$build/codexbar-settings" "$HOME/.local/bin/codexbar-settings.new"
mv -f "$HOME/.local/bin/codexbar-settings.new" "$HOME/.local/bin/codexbar-settings"
echo "Installed helpers, native settings, provider marks and $indicators_dir/libcodexbar.so"

if ! "$restart"; then
  echo 'Installed without restarting Wingpanel or CodexBar. The panel module loads at next login (or an explicit --restart).'
  exit 0
fi
if pgrep -x io.elementary.w >/dev/null; then
  pkill -x io.elementary.w || true
  for _ in 1 2 3 4 5 6 7 8 9 10; do sleep 1; pgrep -x io.elementary.w >/dev/null && break; done
fi
pgrep -x io.elementary.w >/dev/null || { setsid -f io.elementary.wingpanel >/dev/null 2>&1; sleep 2; }
# The daemon and helpers do not need restarting to load a panel module. Never quit a running daemon here.
if ! pgrep -f 'codexbar-linux --background' >/dev/null; then
  setsid -f "$HOME/.local/bin/codexbar-linux" --background >/dev/null 2>&1
fi
sleep 2
pgrep -x io.elementary.w >/dev/null && pgrep -f 'codexbar-linux --background' >/dev/null \
  && echo 'Wingpanel reloaded; CodexBar is running.' || { echo 'Reload check failed.' >&2; exit 1; }
