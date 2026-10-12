#!/bin/bash
# Official auto-updating ARM64 beta; no root or third-party repackaging.
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fLsS https://updates.signal.org/desktop/signal-desktop-beta_arm64.AppImage -o "$work/signal.AppImage"
curl -fLsS https://updates.signal.org/desktop/signal-desktop-beta_arm64.AppImage.gpg -o "$work/signal.gpg"
curl -fLsS https://updates.signal.org/static/desktop/appimage.asc -o "$work/key.asc"
mkdir -m700 "$work/gnupg"
gpg --homedir "$work/gnupg" --import "$work/key.asc"
gpg --homedir "$work/gnupg" --status-fd 1 --verify "$work/signal.gpg" "$work/signal.AppImage" > "$work/status"
grep -q '^\[GNUPG:\] VALIDSIG 4B16B7232DFAA439AD791002EF9F501F13EED94C ' "$work/status"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
install -m755 "$work/signal.AppImage" "$HOME/.local/bin/signal-desktop"
cat > "$HOME/.local/share/applications/signal-desktop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Signal Beta
Comment=Official Signal Desktop ARM64 beta
Exec="$HOME/.local/bin/signal-desktop" --use-tray-icon %U
Terminal=false
Categories=Network;InstantMessaging;
StartupWMClass=Signal Beta
EOF
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
bash "$repo/mseries/install-signal-integration.sh"
echo 'Installed Signal Beta. Link your phone when it opens.'
