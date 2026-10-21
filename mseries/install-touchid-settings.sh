#!/usr/bin/env bash
# Touch ID in System Settings (M-series, Aurora SEP kernel).
#
#   bash mseries/install-touchid-settings.sh              # build and install the page
#   bash mseries/install-touchid-settings.sh --uninstall  # remove it
#
# Adds Settings -> Personal -> Touch ID: add and remove fingerprints, and choose
# whether sudo and system authorization prompts accept a finger. It is a
# Switchboard plug (GTK 4 + libadwaita), built the same way as Work Mode.
#
# Installs: the plug into Switchboard's personal/ directory, the PAM helper into
# /usr/local/sbin and a polkit action so the password prompt explains itself.
# Nothing here touches the kernel, bootloader or device tree, and PAM is changed
# only when a switch on the page is turned on. Enrolled fingerprints are kept on
# uninstall; clear them with: fprintd-delete "$USER"
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/touchid-settings"
plugsdir=$(pkg-config --variable=plugsdir switchboard-3 2>/dev/null || true)
plug="$plugsdir/personal/libmseries-touchid.so"
helper=/usr/local/sbin/mseries-aurora-touchid-apply-pam
policy="$(pkg-config --variable=datadir glib-2.0 2>/dev/null || echo /usr/share)/polkit-1/actions/org.mseries.touchid.policy"

# The earlier stand-alone app probed the sensor at launch; the Settings page
# replaces it. Remove only the per-user launcher it installed.
old_app="$HOME/.local/bin/mseries-touchid-settings"
old_desktop="$HOME/.local/share/applications/mseries-touchid-settings.desktop"

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f "$plug" "$policy"
  # The helper is also what removes pam_fprintd, so leave it if PAM still uses it.
  if grep -qs pam_fprintd /etc/pam.d/sudo /etc/pam.d/polkit-1; then
    echo "Kept $helper: /etc/pam.d still has pam_fprintd. Run '$helper --remove' as root, then delete it."
  else
    sudo rm -f "$helper"
  fi
  echo 'Removed Touch ID from System Settings. Enrolled fingerprints were kept.'
  exit 0
fi

for command in meson ninja valac pkg-config; do
  command -v "$command" >/dev/null || { echo "Missing build dependency: $command" >&2; exit 1; }
done
pkg-config --exists switchboard-3 gtk4 'libadwaita-1 >= 1.6' gee-0.8 || {
  echo 'Missing elementary Switchboard build dependencies:' >&2
  echo '  sudo apt install valac meson ninja-build libswitchboard-3-dev libgtk-4-dev libadwaita-1-dev libgee-0.8-dev' >&2
  exit 1
}
command -v fprintd-list >/dev/null || { echo 'Missing fprintd (sudo apt install fprintd).' >&2; exit 1; }

build=$(mktemp -d)
trap 'rm -rf "$build"' EXIT
meson setup "$build" "$src" --prefix=/usr
ninja -C "$build"
sudo ninja -C "$build" install

rm -f "$old_app" "$old_desktop"
command -v update-desktop-database >/dev/null && \
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

echo 'Installed: System Settings -> Personal -> Touch ID.'
echo 'It loads next time Settings is opened. Opening the page wakes the sensor; nothing is'
echo 'enrolled and PAM is unchanged until you add a fingerprint and turn a switch on.'
echo 'Revert: bash mseries/install-touchid-settings.sh --uninstall'
