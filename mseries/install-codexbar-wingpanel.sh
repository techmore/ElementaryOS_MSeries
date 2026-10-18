#!/bin/bash
# Build and install the Pantheon-native CodexBar Wingpanel indicator.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
src="$repo/mseries/codexbar-wingpanel"

if [[ ${1:-} == --uninstall ]]; then
  indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
  sudo rm -f "$indicators_dir/libcodexbar.so"
  sudo rm -f /usr/share/icons/hicolor/scalable/apps/mseries-codexbar-openai-symbolic.svg
  if command -v gtk-update-icon-cache >/dev/null; then
    sudo gtk-update-icon-cache -f /usr/share/icons/hicolor
  fi
  echo 'Removed the CodexBar Wingpanel indicator. Log out and back in to reload Wingpanel.'
  exit 0
fi

mseries_apt_refresh
sudo apt-get install -y meson ninja-build valac pkg-config \
  libwingpanel-9-dev libgranite-7-dev libjson-glib-dev \
  python3-gi gir1.2-granite-7.0 gir1.2-webkit-6.0

mkdir -p "$HOME/.local/lib/codexbar-cli"
install -m 0755 "$repo/mseries/codexbar-opencode-local.py" \
  "$HOME/.local/lib/codexbar-cli/codexbar-opencode-local.py"
install -m 0644 "$repo/mseries/codexbar_cache.py" "$HOME/.local/lib/codexbar-cli/codexbar_cache.py"
install -m 0644 "$repo/mseries/codexbar_claude_history.py" "$HOME/.local/lib/codexbar-cli/codexbar_claude_history.py"
install -m 0755 "$repo/mseries/codexbar-sessions.py" \
  "$HOME/.local/lib/codexbar-cli/codexbar-sessions.py"
install -m 0755 "$repo/mseries/codexbar-accounts.py" "$HOME/.local/lib/codexbar-cli/codexbar-accounts.py"
install -m 0755 "$repo/mseries/codexbar-claude.py" "$HOME/.local/lib/codexbar-cli/codexbar-claude.py"

for tool in meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo '  sudo apt install meson ninja-build valac libwingpanel-9-dev libgranite-7-dev libjson-glib-dev' >&2
    exit 1
  }
done

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/codexbar-wingpanel.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
meson setup "$build_dir" "$src" --prefix=/usr
ninja -C "$build_dir"
meson test -C "$build_dir" --print-errorlogs
sudo ninja -C "$build_dir" install
sudo rm -f /usr/share/icons/hicolor/scalable/apps/mseries-codexbar-openai.svg
if command -v gtk-update-icon-cache >/dev/null; then
  sudo gtk-update-icon-cache -f /usr/share/icons/hicolor
fi
echo 'Installed CodexBar in Wingpanel. The dropdown shows compact quota rows with reset times, pace tooltips, and account actions.'
