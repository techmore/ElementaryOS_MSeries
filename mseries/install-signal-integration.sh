#!/usr/bin/env bash
# Repair Electron's lowercase application identity and install its bundled icon.
set -euo pipefail
appdir=${MSERIES_SIGNAL_APPDIR:-$HOME/.local/lib/signal-desktop-beta}
atomic=${MSERIES_SIGNAL_ATOMIC:-0}
mode_file="$HOME/.local/state/mseries-signal/deployment-mode"
if [[ -z ${MSERIES_SIGNAL_APPDIR:-} && -f $mode_file && $(cat "$mode_file") == atomic ]]; then
  appdir="$HOME/.local/lib/mseries-apps/signal-desktop-beta/current/app"
  atomic=1
fi
app="$appdir/AppRun"
test -x "$app" || { echo 'Install Signal with mseries/install-signal.sh first.' >&2; exit 1; }
icon="$appdir/usr/share/icons/hicolor/1024x1024/apps/signal-desktop-beta.png"
test -s "$icon"
install -d "$HOME/.local/libexec"
install -m755 "$(dirname "${BASH_SOURCE[0]}")/signal-launcher.sh" "$HOME/.local/libexec/mseries-signal-launcher"
install -m644 "$(dirname "${BASH_SOURCE[0]}")/signal-accent.py" "$HOME/.local/libexec/mseries-signal-accent.py"
launcher="$HOME/.local/libexec/mseries-signal-launcher %U"
icon_destination="$HOME/.local/share/icons/hicolor/1024x1024/apps/signal-desktop-beta.png"
install -d "$(dirname "$icon_destination")"
# The icon follows the selected release too, including after rollback.
ln -sfn "$icon" "$icon_destination"
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
Exec=$launcher
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
if [[ $atomic == 1 ]]; then
  printf 'atomic\n' >"$mode_file.tmp"
else
  printf 'legacy\n' >"$mode_file.tmp"
fi
mv -f "$mode_file.tmp" "$mode_file"
command -v update-desktop-database >/dev/null && update-desktop-database "$HOME/.local/share/applications"
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
# Recolour Signal's blue to the elementary stylesheet palette. The launcher refreshes this
# mutable user install at the next open after the system accent changes. Atomic
# releases stay immutable and retain their upstream colors.
if [[ $atomic != 1 ]]; then
  python3 "$HOME/.local/libexec/mseries-signal-accent.py" --appdir "$appdir" || echo 'Signal accent recolour skipped' >&2
fi
echo 'Repaired Signal Beta desktop identity. The system accent refreshes when Signal next opens.'
