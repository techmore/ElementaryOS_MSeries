#!/bin/bash
# Discord's official amd64 app, run under FEX inside muvm (needs install-muvm.sh first).
# Discord's own Electron 42 binary dies with SIGTRAP at startup under FEX 2610 (stock Electron 42.11.12 does the
# same), while Electron 43 runs fine. So this takes Discord's official, unmodified app.asar and modules (fetched by
# the deb's own updater_bootstrap) and runs them on stock Electron 43.2.0 x86-64 (SHA-256 pinned).
# Status 2026-10-18: Discord 1.0.162 starts and stays up for 40 s headless-ish; login, voice (native modules
# were built for Electron 42), rendering and performance are NOT verified. Launcher: ~/.local/bin/discord-official.
#   install-discord-official.sh              install
#   install-discord-official.sh --uninstall  remove (keeps ~/.config/discord)
set -euo pipefail
dir=$HOME/.local/lib/discord-official
launcher=$HOME/.local/bin/discord-official
desktop=$HOME/.local/share/applications/discord-official.desktop
if [[ ${1:-} == --uninstall ]]; then
  rm -rf "$dir" "$launcher" "$desktop"
  echo 'Removed. ~/.config/discord kept.'
  exit 0
fi
[[ -z ${1:-} ]] || { echo 'Usage: install-discord-official.sh [--uninstall]' >&2; exit 2; }
command -v muvm >/dev/null || { echo 'Run mseries/install-muvm.sh first.' >&2; exit 1; }
version=1.0.162
deb_sha256=e7f346569784ef47eaa530c058d810bef686c7c063efcee6493d56d138f139cc
electron=43.2.0
electron_sha256=f77ca6ed67bbc68702b69b56ad499bca6ae090705ade7d04f0ac545e409dec68
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fLsS "https://stable.dl2.discordapp.net/apps/linux/$version/discord-$version.deb" -o "$work/discord.deb"
echo "$deb_sha256  $work/discord.deb" | sha256sum -c -
curl -fLsS "https://github.com/electron/electron/releases/download/v$electron/electron-v$electron-linux-x64.zip" \
  -o "$work/electron.zip"
echo "$electron_sha256  $work/electron.zip" | sha256sum -c -
mkdir -p "$work/deb" "$HOME/.config/discord" "$HOME/.local/bin" "$HOME/.local/share/applications"
dpkg-deb -x "$work/discord.deb" "$work/deb"
# Official bootstrap downloads the real app into ~/.config/discord/app-*/ (resources/app.asar + modules/).
muvm -- "$work/deb/usr/share/discord/updater_bootstrap" --no-zenity "$HOME/.config/discord" stable https://updates.discord.com/
app=$(ls -d "$HOME"/.config/discord/app-*/ | sort -V | tail -1)
new=$dir.new
rm -rf "$new"
mkdir -p "$new"
unzip -q "$work/electron.zip" -d "$new"
cp -a "$app/resources/." "$new/resources/"
cp -a "$app/modules" "$new/modules"
install -Dm644 "$work/deb/usr/share/discord/discord.png" "$HOME/.local/share/icons/hicolor/512x512/apps/discord-official.png"
rm -rf "$dir.old"
[[ ! -e $dir ]] || mv "$dir" "$dir.old"
mv "$new" "$dir"
rm -rf "$dir.old"
tmp=$(mktemp "$HOME/.local/bin/.discord-official.XXXXXX")
# --no-sandbox: the setuid sandbox and user namespaces are unavailable under FEX in the microVM.
printf '#!/bin/bash\ncd %q\nexec muvm -- %q --no-sandbox "$@"\n' "$dir" "$dir/electron" >"$tmp"
chmod 755 "$tmp"
mv -f "$tmp" "$launcher"
cat >"$desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Discord (official, x86 emulated)
Comment=Official Discord $version under FEX in a muvm microVM
Exec=$launcher %U
Icon=discord-official
Terminal=false
Categories=Network;InstantMessaging;Chat;
StartupWMClass=discord
MimeType=x-scheme-handler/discord;
X-MSeries-Managed=true
EOF
update-desktop-database "$(dirname "$desktop")" 2>/dev/null || true
echo "Installed official Discord $version on Electron $electron. Run 'discord-official'."
