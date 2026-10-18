#!/bin/bash
# Native ARM64 Discord. Discord Inc. ships no Linux ARM64 build (its tarball/deb are x86_64 only), so this
# installs Vesktop (https://github.com/Vencord/Vesktop, GPL-3.0), an Electron Discord client that publishes
# aarch64 releases. The release is pinned and its SHA-256 is checked before anything is installed.
#   install-discord.sh              install or update to the pinned version
#   install-discord.sh --uninstall  remove (keeps ~/.config/vesktop, your login and settings)
set -euo pipefail
version=1.6.7
sha256=260144352ce10291ee7ecd0b8aa060f3e36a0d8a9c8f6b509db244ee6c36a2ae
appdir=$HOME/.local/lib/vesktop
launcher=$HOME/.local/bin/discord
desktop=$HOME/.local/share/applications/discord.desktop
icon=$HOME/.local/share/icons/hicolor/scalable/apps/discord.svg
if [[ ${1:-} == --uninstall ]]; then
  rm -rf "$appdir" "$launcher" "$desktop" "$icon"
  echo 'Removed Discord (Vesktop). ~/.config/vesktop kept.'
  exit 0
fi
[[ -z ${1:-} ]] || { echo 'Usage: install-discord.sh [--uninstall]' >&2; exit 2; }
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
asset="Vesktop-${version}-arm64.AppImage"
curl -fLsS "https://github.com/Vencord/Vesktop/releases/download/v${version}/${asset}" -o "$work/$asset"
echo "$sha256  $work/$asset" | sha256sum -c -
chmod 755 "$work/$asset"
# Extract instead of running the AppImage: no FUSE needed and the app starts faster.
(cd "$work" && "./$asset" --appimage-extract >/dev/null)
new="$appdir.new"
rm -rf "$new"
mkdir -p "$(dirname "$appdir")" "$HOME/.local/bin" "$(dirname "$desktop")" "$(dirname "$icon")"
cp -a "$work/squashfs-root" "$new"
rm -rf "$appdir.old"
[[ ! -e $appdir ]] || mv "$appdir" "$appdir.old"
mv "$new" "$appdir"
rm -rf "$appdir.old"
install -m644 "$appdir/usr/share/icons/hicolor/scalable/apps/vesktop.svg" "$icon"
# Native Wayland via the Electron ozone hint; Vesktop's own AppRun passes the rest through.
tmp=$(mktemp "$HOME/.local/bin/.discord.XXXXXX")
printf '#!/bin/bash\nexec %q --ozone-platform-hint=auto "$@"\n' "$appdir/AppRun" >"$tmp"
chmod 755 "$tmp"
mv -f "$tmp" "$launcher"
cat >"$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Discord
Comment=Discord for ARM64 (Vesktop ${version})
Exec=$launcher %U
Icon=discord
Terminal=false
Categories=Network;InstantMessaging;Chat;
StartupWMClass=vesktop
MimeType=x-scheme-handler/discord;
X-MSeries-Managed=true
EOF
update-desktop-database "$(dirname "$desktop")" 2>/dev/null || true
echo "Installed Discord (Vesktop ${version}, native aarch64). Launch it from the app menu or run 'discord'."
