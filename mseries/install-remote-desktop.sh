#!/usr/bin/env bash
# Build and install Remote Desktop (WebRTC host daemon, native app, panel and
# taskbar indicator) without touching the running desktop:
#   * user-level pieces go to ~/.local and take effect on next use;
#   * remote access stays OFF (nothing listens) until the owner turns it on;
#   * the Wingpanel module needs sudo and loads at next login (--panel).
#
#   bash mseries/install-remote-desktop.sh [--build-only] [--panel] [--uninstall]
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/remote-desktop"
bin="$HOME/.local/bin"
panel=false
build_only=false
case ${1:-} in
  '') ;;
  --build-only) build_only=true ;;
  --panel) panel=true ;;
  --uninstall)
    systemctl --user disable --now mseries-remote-hostd.service 2>/dev/null || true
    pkill -f 'mseries-remote --background' 2>/dev/null || true
    rm -f "$bin/mseries-remote-hostd" "$bin/mseries-remote" "$bin/tm-remote-viewer" \
      "$HOME/.config/systemd/user/mseries-remote-hostd.service" \
      "$HOME/.local/share/dbus-1/services/io.elementary.mseries.Remote.service" \
      "$HOME/.local/share/applications/io.github.techmore.RemoteDesktop.desktop" \
      "$HOME/.config/autostart/io.github.techmore.RemoteDesktop.desktop" \
      "$HOME/.local/share/icons/hicolor/symbolic/apps/mseries-remote-symbolic.svg" \
      "$HOME/.local/share/icons/hicolor/symbolic/apps/mseries-remote-sharing-symbolic.svg"
    systemctl --user daemon-reload
    echo 'Removed Remote Desktop from ~/.local. The Wingpanel module (if installed) is left: sudo rm "$(pkg-config --variable=indicatorsdir wingpanel-9)/libremote.so"'
    exit 0 ;;
  *) echo 'Usage: install-remote-desktop.sh [--build-only] [--panel] [--uninstall]' >&2; exit 2 ;;
esac

for command in cargo meson ninja valac pkg-config; do
  command -v "$command" >/dev/null || { echo "Missing build dependency: $command" >&2; exit 1; }
done
pkg-config --exists gtk4 granite-7 json-glib-1.0 || { echo 'Missing libgtk-4-dev / libgranite-7-dev / libjson-glib-dev' >&2; exit 1; }
command -v gst-launch-1.0 >/dev/null || echo 'Note: gst-launch-1.0 (gstreamer1.0-tools + gstreamer1.0-pipewire) is needed for screen capture.' >&2

target=${CARGO_TARGET_DIR:-$(mktemp -d "${TMPDIR:-/tmp}/remote-desktop-target.XXXXXX")}
build=$(mktemp -d "${TMPDIR:-/tmp}/remote-desktop-native.XXXXXX")
trap 'rm -rf "$build"; [ -n "${CARGO_TARGET_DIR:-}" ] || rm -rf "$target"' EXIT
(cd "$src" && CARGO_TARGET_DIR="$target" cargo build --release --locked)
meson setup "$build" "$src/native" --prefix="$HOME/.local" >/dev/null
ninja -C "$build" >/dev/null
meson test -C "$build" --print-errorlogs

"$build_only" && { echo 'Built and tested; nothing installed.'; exit 0; }

install -Dm0755 "$target/release/mseries-remote-hostd" "$bin/mseries-remote-hostd"
install -Dm0755 "$target/release/tm-remote-viewer" "$bin/tm-remote-viewer"
install -Dm0755 "$build/mseries-remote" "$bin/mseries-remote"
install -Dm0644 "$src/deploy/mseries-remote-hostd.service" "$HOME/.config/systemd/user/mseries-remote-hostd.service"
mkdir -p "$HOME/.local/share/dbus-1/services"
sed "s|@BIN@|$bin|" "$src/deploy/io.elementary.mseries.Remote.service.in" \
  >"$HOME/.local/share/dbus-1/services/io.elementary.mseries.Remote.service"
install -Dm0644 "$src/native/data/io.github.techmore.RemoteDesktop.desktop" "$HOME/.local/share/applications/io.github.techmore.RemoteDesktop.desktop"
install -Dm0644 "$src/native/data/io.github.techmore.RemoteDesktop.autostart.desktop" "$HOME/.config/autostart/io.github.techmore.RemoteDesktop.desktop"
for icon in mseries-remote-symbolic mseries-remote-sharing-symbolic; do
  install -Dm0644 "$src/native/data/$icon.svg" "$HOME/.local/share/icons/hicolor/symbolic/apps/$icon.svg"
done
systemctl --user daemon-reload
"$bin/mseries-remote-hostd" check || true

if "$panel"; then
  indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
  # install(1) replaces the file, so a loaded module is never truncated in place.
  sudo install -m 0755 "$build/libremote.so" "$indicators_dir/libremote.so"
  echo "Installed $indicators_dir/libremote.so; Wingpanel loads it at next login (not restarted)."
fi
echo 'Installed Remote Desktop to ~/.local. Remote access is OFF: open "Remote Desktop" and turn it on.'
echo 'The Work Mode taskbar indicator ships with the dock build (mseries/dock-taskbar); it loads with the next dock deployment.'
