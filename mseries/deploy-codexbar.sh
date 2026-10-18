#!/bin/bash
# Make the running desktop use what is in the repo for the CodexBar custom port. Run after every push that
# touches CodexBar: installs the helpers, rebuilds and installs the Wingpanel module, then restarts
# Wingpanel and the CodexBar app so this session is actually running the new code.
#   bash mseries/deploy-codexbar.sh [--no-restart]
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
lib="$HOME/.local/lib/codexbar-cli"
mkdir -p "$lib"
for helper in codexbar-opencode-local.py codexbar-sessions.py codexbar-accounts.py codexbar-claude.py; do
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

[[ ${1:-} == --no-restart ]] && { echo 'Not restarting; Wingpanel loads the new module at next login.'; exit 0; }
if pgrep -x io.elementary.w >/dev/null; then
  pkill -x io.elementary.w || true   # the session respawns it; fall back to launching it ourselves
  for _ in 1 2 3 4 5 6 7 8 9 10; do sleep 1; pgrep -x io.elementary.w >/dev/null && break; done
  pgrep -x io.elementary.w >/dev/null || { setsid -f io.elementary.wingpanel >/dev/null 2>&1; sleep 2; }
fi
if pgrep -f 'codexbar-linux --background' >/dev/null; then
  "$HOME/.local/bin/codexbar-linux" --quit >/dev/null 2>&1 || true
  sleep 2
fi
setsid -f "$HOME/.local/bin/codexbar-linux" --background >/dev/null 2>&1
sleep 2
pgrep -x io.elementary.w >/dev/null && pgrep -f 'codexbar-linux --background' >/dev/null \
  && echo 'Wingpanel and CodexBar are running the new build.' || { echo 'Restart check failed.' >&2; exit 1; }
