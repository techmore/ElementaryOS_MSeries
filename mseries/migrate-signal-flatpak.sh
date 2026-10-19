#!/usr/bin/env bash
# Move the Signal account from the Flatpak (org.signal.Signal) to the native ARM64 Signal Beta,
# keeping history and the device link (no re-linking).
#   bash mseries/migrate-signal-flatpak.sh            # migrate (both Signals must be closed)
#   bash mseries/migrate-signal-flatpak.sh --check    # report what would happen, change nothing
#   bash mseries/migrate-signal-flatpak.sh --rollback # show the Flatpak again, set the native profile aside
#
# The copied profile IS the linked device: never run the Flatpak and the native app at the same time
# afterwards, or both talk to Signal as one device and sessions break. That is why the Flatpak launcher
# is hidden. The Flatpak's own data is left untouched as a backup; it goes stale as soon as the native
# app sends or receives, so --rollback after real use means Signal may need to re-link.
set -euo pipefail
mode=migrate
case ${1:-} in
  --check) mode=check ;;
  --rollback) mode=rollback ;;
  '') ;;
  *) echo 'Usage: migrate-signal-flatpak.sh [--check|--rollback]' >&2; exit 2 ;;
esac
src="$HOME/.var/app/org.signal.Signal/config/Signal"
dst="$HOME/.config/Signal Beta"
apps="$HOME/.local/share/applications"
hide="$apps/org.signal.Signal.desktop"
export_desktop=
for dir in "$HOME/.local/share/flatpak/exports/share/applications" /var/lib/flatpak/exports/share/applications; do
  [[ -f $dir/org.signal.Signal.desktop ]] && { export_desktop=$dir/org.signal.Signal.desktop; break; }
done
native="$HOME/.local/lib/signal-desktop-beta/AppRun"
[[ -x $native ]] || native="$HOME/.local/lib/mseries-apps/signal-desktop-beta/current/app/AppRun"

running() {
  if command -v flatpak >/dev/null && flatpak ps --columns=application 2>/dev/null | grep -qx org.signal.Signal; then
    echo 'the Flatpak Signal'; return 0
  fi
  if pgrep -f 'signal-desktop-beta/(current/app/)?signal-desktop-beta' >/dev/null; then
    echo 'the native Signal Beta'; return 0
  fi
  return 1
}

if [[ $mode == rollback ]]; then
  if who=$(running); then echo "Quit $who first." >&2; exit 1; fi
  if [[ -f $hide ]] && grep -q '^X-MSeries-Managed=true$' "$hide"; then rm -f "$hide"; fi
  if [[ -d $dst ]]; then
    aside="$dst.set-aside-$(date +%Y%m%d-%H%M%S)"
    mv "$dst" "$aside"
    echo "Native profile set aside at $aside (not deleted)."
  fi
  command -v update-desktop-database >/dev/null && update-desktop-database "$apps" || true
  echo 'Flatpak Signal is visible again. If the native app was used, Signal may ask to re-link.'
  exit 0
fi

[[ -f $src/config.json && -d $src/sql ]] || { echo "No Flatpak Signal profile at $src" >&2; exit 1; }
[[ -x $native ]] || { echo 'Install the native app first: bash mseries/install-signal.sh' >&2; exit 1; }
if [[ -d $dst/sql ]]; then
  echo "$dst already has a Signal profile; refusing to overwrite it." >&2
  echo 'Use --rollback to set it aside first if you really want to migrate again.' >&2
  exit 1
fi
if who=$(running); then
  echo "Quit $who first (its database must not be copied while open)." >&2
  [[ $mode == check ]] || exit 1
fi
size=$(du -sh "$src" | cut -f1)
if [[ $mode == check ]]; then
  echo "Would copy $src ($size) to $dst, skipping caches and lock files."
  echo "Would hide the Flatpak launcher with $hide (Flatpak data kept)."
  exit 0
fi

tmp="$dst.migrating"
rm -rf "$tmp"
mkdir -p "$(dirname "$dst")"
# Caches and Chromium's single-instance locks are per install; everything else is the account.
rsync -a \
  --exclude 'Singleton*' --exclude 'Cache/' --exclude 'Code Cache/' --exclude 'GPUCache/' \
  --exclude 'DawnGraphiteCache/' --exclude 'DawnWebGPUCache/' --exclude 'GPUPersistentCache/' \
  --exclude 'Crashpad/' --exclude 'temp/' --exclude 'logs/' \
  "$src/" "$tmp/"
chmod 700 "$tmp"
mv "$tmp" "$dst"

if [[ -n $export_desktop ]]; then
  mkdir -p "$apps"
  # Keys go right under [Desktop Entry]: appended at the end they could land in a [Desktop Action] group.
  sed '/^\[Desktop Entry\]$/a NoDisplay=true\nX-MSeries-Managed=true' "$export_desktop" > "$hide"
  command -v update-desktop-database >/dev/null && update-desktop-database "$apps" || true
fi
echo "Copied the Signal account ($size) to $dst."
echo 'The Flatpak launcher is hidden; open "Signal Beta". Do not start the Flatpak Signal again.'
