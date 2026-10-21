#!/bin/bash
# Install the optional elementary OS GitHub repository status indicator.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9 2>/dev/null || true)
prefix=$(pkg-config --variable=prefix wingpanel-9 2>/dev/null || echo /usr)
icon_theme_dir="$prefix/share/icons/hicolor"

if [[ ${1:-} == --uninstall ]]; then
  [[ -n $indicators_dir ]] && sudo rm -f "$indicators_dir/librepobar.so"
  sudo rm -f "$icon_theme_dir/symbolic/apps/github-symbolic.svg"
  for icon in globe commit issue pull; do
    sudo rm -f "$icon_theme_dir/symbolic/apps/mseries-repobar-$icon-symbolic.svg"
  done
  if command -v gtk-update-icon-cache >/dev/null; then
    sudo gtk-update-icon-cache -f "$icon_theme_dir" >/dev/null
  fi
  rm -f "$HOME/.local/bin/mseries-repobar" "$HOME/.local/bin/mseries-repobar-settings" "$HOME/.local/lib/mseries/repobar.py" \
    "$HOME/.local/share/applications/io.github.techmore.RepoBar.Settings.desktop"
  echo 'Removed the RepoBar Wingpanel indicator and per-user helper. Cached GitHub status remains in ~/.cache/mseries/repobar/snapshot.json.'
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

install -d -m 0755 "$HOME/.local/lib/mseries" "$HOME/.local/bin"
install -m 0644 "$repo/mseries/repobar.py" "$HOME/.local/lib/mseries/repobar.py"
cat > "$HOME/.local/bin/mseries-repobar.new" <<'WRAPPER'
#!/bin/sh
exec /usr/bin/python3 "$HOME/.local/lib/mseries/repobar.py" "$@"
WRAPPER
chmod 0755 "$HOME/.local/bin/mseries-repobar.new"
mv -f "$HOME/.local/bin/mseries-repobar.new" "$HOME/.local/bin/mseries-repobar"

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/mseries-repobar.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
meson setup "$build_dir" "$repo/mseries/repobar-wingpanel" --prefix=/usr
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
