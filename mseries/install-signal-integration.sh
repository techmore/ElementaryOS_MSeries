#!/usr/bin/env bash
# Repair Electron's lowercase application identity and install its bundled icon.
set -euo pipefail
app="$HOME/.local/bin/signal-desktop"
test -x "$app" || { echo 'Install Signal with mseries/install-signal.sh first.' >&2; exit 1; }
work=$(mktemp -d /tmp/mseries-signal-integration.XXXXXX)
trap 'rm -rf "$work"' EXIT
(cd "$work" && "$app" --appimage-extract 'usr/share/icons/hicolor/1024x1024/apps/signal-desktop-beta.png' >/dev/null)
icon="$work/squashfs-root/usr/share/icons/hicolor/1024x1024/apps/signal-desktop-beta.png"
test -s "$icon"
install -Dm644 "$icon" "$HOME/.local/share/icons/hicolor/1024x1024/apps/signal-desktop-beta.png"
mkdir -p "$HOME/.local/share/applications" "$HOME/.local/state/mseries-signal"
canonical="$HOME/.local/share/applications/signal-desktop.desktop"
if [[ -f $canonical && ! -e "$HOME/.local/state/mseries-signal/desktop-before-integration" ]]; then
  cp "$canonical" "$HOME/.local/state/mseries-signal/desktop-before-integration"
fi
cat > "$canonical" <<EOF
[Desktop Entry]
Type=Application
Name=Signal Beta
Comment=Official Signal Desktop ARM64 beta
Exec="$app" --use-tray-icon %U
Icon=signal-desktop-beta
Terminal=false
Categories=Network;InstantMessaging;Chat;
StartupWMClass=signal beta
MimeType=x-scheme-handler/sgnl;x-scheme-handler/signalcaptcha;
X-MSeries-Managed=true
EOF
# Wayland/Electron identifies this window as "signal beta"; the dock resolves
# that identity to a desktop filename, independent of StartupWMClass on X11.
for id in 'signal beta' signal-desktop-beta; do
  alias="$HOME/.local/share/applications/$id.desktop"
  if [[ -f $alias ]] && ! grep -q '^X-MSeries-Managed=true$' "$alias"; then
    echo "Preserving existing $alias" >&2
    continue
  fi
  cp "$canonical" "$alias"
  echo 'NoDisplay=true' >> "$alias"
done
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications"
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
echo 'Repaired Signal Beta icon and desktop identity; no app restart or sign-in required.'
