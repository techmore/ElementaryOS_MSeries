#!/bin/bash
# Rebuild RepoBar's Wingpanel indicator and per-user helper from this checkout, without apt.
# Wingpanel loads a replaced module at next login. Use --restart only for an intentional panel reload.
#   bash mseries/deploy-repobar.sh [--restart|--no-restart]
set -euo pipefail
restart=false
case ${1:-} in
  ''|--no-restart) ;;
  --restart) restart=true ;;
  *) echo 'Usage: deploy-repobar.sh [--restart|--no-restart]' >&2; exit 2 ;;
esac

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
install -d -m 0755 "$HOME/.local/lib/mseries"
install -m 0644 "$repo/mseries/repobar.py" "$HOME/.local/lib/mseries/repobar.py"

build=$(mktemp -d "${TMPDIR:-/tmp}/mseries-repobar.XXXXXX")
trap 'rm -rf "$build"' EXIT
meson setup "$build" "$repo/mseries/repobar-wingpanel" --prefix=/usr >/dev/null
ninja -C "$build" librepobar.so >/dev/null
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
sudo install -m 0755 "$build/librepobar.so" "$indicators_dir/librepobar.so"
sudo install -m 0644 "$repo/mseries/repobar-wingpanel/icons/github-symbolic.svg" \
  /usr/share/icons/hicolor/symbolic/apps/github-symbolic.svg
sudo gtk-update-icon-cache -f /usr/share/icons/hicolor >/dev/null

if ! "$restart"; then
  echo 'Installed without restarting Wingpanel. The RepoBar module loads at next login (or an explicit --restart).'
  exit 0
fi
pkill -x io.elementary.w || true
sleep 1
pgrep -x io.elementary.w >/dev/null || { setsid -f io.elementary.wingpanel >/dev/null 2>&1; sleep 2; }
echo 'Wingpanel reloaded with the new RepoBar module.'
