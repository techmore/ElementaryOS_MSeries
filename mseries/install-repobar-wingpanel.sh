#!/bin/bash
# Install the optional elementary OS GitHub repository status indicator.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9 2>/dev/null || true)
prefix=$(pkg-config --variable=prefix wingpanel-9 2>/dev/null || echo /usr)
icon_theme_dir="$prefix/share/icons/hicolor"

if [[ ${1:-} == --uninstall ]]; then
  indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
  if [[ -f "$indicators_dir/libmseries-t3.so" || -f "$indicators_dir/../mseries-pending-indicators/libmseries-t3.so" ]]; then
    sudo rm -f "$indicators_dir/librepobar.so"
    echo 'Standalone module retired; shared settings, helpers and icons retained for T3.'
    exit 0
  fi
  [[ -n $indicators_dir ]] && sudo rm -f "$indicators_dir/librepobar.so"
  sudo rm -f "$icon_theme_dir/symbolic/apps/github-symbolic.svg"
  for icon in globe commit issue pull; do
    sudo rm -f "$icon_theme_dir/symbolic/apps/mseries-repobar-$icon-symbolic.svg"
  done
  if command -v gtk-update-icon-cache >/dev/null; then
    sudo gtk-update-icon-cache -f "$icon_theme_dir" >/dev/null
  fi
  rm -f "$HOME/.local/bin/mseries-repobar-settings" \
    "$HOME/.local/share/applications/io.github.techmore.RepoBar.Settings.desktop"
  if ! command -v claude-pantheon-rs >/dev/null && ! command -v claude-pantheon-sdk >/dev/null; then
    rm -f "$HOME/.local/bin/mseries-repobar" "$HOME/.local/lib/mseries/repobar.py"
  fi
  echo 'Removed the RepoBar indicator. The read-only helper is retained when T3 uses it; cached GitHub status remains.'
  exit 0
fi

mseries_apt_refresh
sudo apt-get install -y gh meson ninja-build valac pkg-config \
  libwingpanel-9-dev libgranite-7-dev libjson-glib-dev libgtk-3-bin

for tool in gh meson ninja valac pkg-config gtk-update-icon-cache; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool; install the packages listed above and retry." >&2
    exit 1
  }
done

install -Dm0755 "$repo/mseries/repobar.py" "$HOME/.local/bin/mseries-repobar"
# Retire the old wrapper payload; both T3 and RepoBar use the same executable.
rm -f "$HOME/.local/lib/mseries/repobar.py"

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/mseries-repobar.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
install_indicator=true
[[ ! -f "$indicators_dir/libmseries-t3.so" && ! -f "$indicators_dir/../mseries-pending-indicators/libmseries-t3.so" ]] || install_indicator=false
meson setup "$build_dir" "$repo/mseries/repobar-wingpanel" --prefix=/usr -Dinstall_indicator="$install_indicator"
ninja -C "$build_dir"
sudo ninja -C "$build_dir" install
install -m 0755 "$build_dir/mseries-repobar-settings" "$HOME/.local/bin/mseries-repobar-settings"
sudo gtk-update-icon-cache -f "$icon_theme_dir"

# RepoBar Settings launcher, so the preferences stay reachable while the panel module is hidden.
install -d -m 0755 "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/io.github.techmore.RepoBar.Settings.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=RepoBar Settings
Comment=GitHub accounts, dashboard and notifications for RepoBar
Exec=$HOME/.local/bin/mseries-repobar-settings
Icon=github-symbolic
Terminal=false
Categories=Settings;Development;
StartupNotify=true
DESKTOP

echo 'RepoBar is installed in Wingpanel. Authenticate once with `gh auth login`, then reopen the menu.'
echo 'The indicator only reads GitHub data and keeps a private, 5-minute local cache.'

if [[ $install_indicator == false ]]; then
  bash "$repo/mseries/install-t3-wingpanel.sh"
fi
