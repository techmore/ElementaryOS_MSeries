#!/usr/bin/env bash
# Native full-height panel and compact dock for the 14-inch M1 Pro.
# --build-only compiles both without installing; --revert restores the profile.
# Full height is prepared on the same running kernel, without a forced reboot.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mode=${1:-install}
state=${XDG_STATE_HOME:-$HOME/.local/state}/mseries-desktop-space
wrapper=$HOME/.local/bin/io.elementary.dock
dock_prefix=$HOME/.local/lib/mseries/dock
[[ $EUID != 0 ]] || { echo 'Run as the desktop user; system installation uses sudo.' >&2; exit 2; }
case $mode in install|--build-only|--revert) ;; *) echo "Usage: $0 [--build-only|--revert]" >&2; exit 2;; esac
if [[ $mode == --revert ]]; then
  sudo python3 "$repo/mseries/display-space/full_height_boot.py" revert
  python3 "$repo/mseries/display-space/dock_profile.py" --revert
  bash "$repo/mseries/install-dock-drawers.sh" --revert
  if [[ -d $state/dock-build ]]; then
    rm -rf -- "$dock_prefix"
    cp -a "$state/dock-build" "$dock_prefix"
    rm -rf -- "$state/dock-build"
  fi
  if [[ -f $state/dock-wrapper ]]; then
    install -Dm755 "$state/dock-wrapper" "$wrapper"
    rm -f "$state/dock-wrapper"
  fi
  bash "$repo/mseries/install-wingpanel-codexbar-left.sh" --uninstall
  rm -f "$state/installed" "$state/backups-saved"
  echo 'Profile restored. Log in again to reload the panel and dock.'
  exit 0
fi
if [[ $mode == --build-only ]]; then
  bash "$repo/mseries/install-wingpanel-codexbar-left.sh" --build-only
  bash "$repo/mseries/install-dock-drawers.sh" --build-only
  exit 0
fi
# Validate boot provenance before installing anything. Never guess a kernel/initrd.
sudo python3 "$repo/mseries/display-space/full_height_boot.py" preview >/dev/null
mkdir -p "$state"
if [[ ! -e $state/backups-saved ]]; then
  [[ ! -f $wrapper ]] || cp -a "$wrapper" "$state/dock-wrapper"
  [[ ! -d $dock_prefix ]] || cp -a "$dock_prefix" "$state/dock-build"
  touch "$state/backups-saved"
fi
bash "$repo/mseries/install-wingpanel-codexbar-left.sh"
bash "$repo/mseries/install-dock-drawers.sh"
python3 "$repo/mseries/display-space/dock_profile.py"
sudo python3 "$repo/mseries/display-space/full_height_boot.py" prepare
touch "$state/installed"
echo 'Native desktop profile installed. Reboot when ready for full height and the new panel/dock.'
echo 'Revert: bash mseries/install-desktop-space.sh --revert'
