#!/bin/bash
# Official signed ARM64 beta. --atomic opts into versioned release deployment.
set -euo pipefail
atomic=0
case ${1:-} in
  --atomic) atomic=1 ;;
  '') ;;
  *) echo 'Usage: install-signal.sh [--atomic]' >&2; exit 2 ;;
esac
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fLsS https://updates.signal.org/desktop/signal-desktop-beta_arm64.AppImage -o "$work/signal.AppImage"
chmod 755 "$work/signal.AppImage"
curl -fLsS https://updates.signal.org/desktop/signal-desktop-beta_arm64.AppImage.gpg -o "$work/signal.gpg"
curl -fLsS https://updates.signal.org/static/desktop/appimage.asc -o "$work/key.asc"
mkdir -m700 "$work/gnupg"
gpg --homedir "$work/gnupg" --import "$work/key.asc"
gpg --homedir "$work/gnupg" --status-fd 1 --verify "$work/signal.gpg" "$work/signal.AppImage" > "$work/status"
grep -q '^\[GNUPG:\] VALIDSIG 4B16B7232DFAA439AD791002EF9F501F13EED94C ' "$work/status"
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
(cd "$work" && ./signal.AppImage --appimage-extract >/dev/null)
if (( atomic )); then
  install -Dm755 "$repo/mseries/atomic-app.py" "$HOME/.local/libexec/mseries-atomic-app"
  python3 "$repo/mseries/atomic-app.py" --app signal-desktop-beta deploy \
    --source "$work/squashfs-root" --entrypoint AppRun \
    --artifact-sha256 "$(sha256sum "$work/signal.AppImage" | cut -d' ' -f1)" \
    --publisher-fingerprint 4B16B7232DFAA439AD791002EF9F501F13EED94C
  appdir="$HOME/.local/lib/mseries-apps/signal-desktop-beta/current/app"
  if [[ -f "$HOME/.local/bin/signal-desktop" && ! -e "$HOME/.local/bin/signal-desktop.before-atomic" ]]; then
    cp -p "$HOME/.local/bin/signal-desktop" "$HOME/.local/bin/signal-desktop.before-atomic"
  fi
  launcher_tmp=$(mktemp "$HOME/.local/bin/.signal-desktop.XXXXXX")
  printf '#!/bin/bash\nexec /usr/bin/python3 %q --app signal-desktop-beta run -- "$@"\n' \
    "$HOME/.local/libexec/mseries-atomic-app" >"$launcher_tmp"
  chmod 755 "$launcher_tmp"
  mv -f "$launcher_tmp" "$HOME/.local/bin/signal-desktop"
else
  install -m755 "$work/signal.AppImage" "$HOME/.local/bin/signal-desktop"
  appdir="$HOME/.local/lib/signal-desktop-beta"
  mkdir -p "$appdir"
  cp -a "$work/squashfs-root/." "$appdir/"
  # The theme patcher restores from this pristine bundle. Reset it on every
  # upstream update so it cannot reapply colors to a previous Signal version.
  cp -p "$appdir/resources/app.asar" "$appdir/resources/app.asar.orig.tmp"
  mv -f "$appdir/resources/app.asar.orig.tmp" "$appdir/resources/app.asar.orig"
  rm -f "$appdir/resources/.mseries-accent"
fi
MSERIES_SIGNAL_APPDIR="$appdir" MSERIES_SIGNAL_ATOMIC="$atomic" bash "$repo/mseries/install-signal-integration.sh"
echo 'Installed Signal Beta. Link your phone when it opens.'
