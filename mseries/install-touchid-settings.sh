#!/usr/bin/env bash
# Touch ID settings for the M-series (Aurora SEP kernel).
#
#   bash mseries/install-touchid-settings.sh           # install the GUI for this user
#   bash mseries/install-touchid-settings.sh --revert  # remove it
#
# A GTK4/libadwaita app that shows every link in the Touch ID chain (kernel,
# device tree, firmware manifests, enclave, calibration, sensor, reader,
# enrolment) and does the two things that need doing: enrol a finger, and put the
# fingerprint into PAM for sudo/polkit/lock.
#
# The PAM step shells out to /usr/bin/aurora-touchid-setup through pkexec, so it
# asks for the admin password rather than needing to be run as root. Nothing here
# touches the kernel, the bootloader or the device tree — those are the
# m1n1/boot.bin patches recorded in aurora-touchid-state.md.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/aurora-touchid"
bin="$HOME/.local/bin/mseries-touchid-settings"
desktop="$HOME/.local/share/applications/mseries-touchid-settings.desktop"

if [[ ${1:-} == --revert ]]; then
  rm -f "$bin" "$desktop"
  echo "Removed Touch ID settings. Enrolled prints and PAM entries are untouched;"
  echo "undo those with: sudo aurora-touchid-setup --remove"
  exit 0
fi

command -v python3 >/dev/null || { echo "Missing python3." >&2; exit 1; }
python3 -c 'import gi; gi.require_version("Gtk","4.0"); gi.require_version("Adw","1")' 2>/dev/null || {
  echo 'Missing GTK4/libadwaita Python bindings:' >&2
  echo '  sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1' >&2
  exit 1
}

python3 -m py_compile "$src/mseries-touchid-settings"
install -Dm755 "$src/mseries-touchid-settings" "$bin"
install -Dm644 "$src/mseries-touchid-settings.desktop" "$desktop"
command -v update-desktop-database >/dev/null && \
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true

echo "Installed. Find it as “Touch ID” in the applications grid."
echo "Revert: bash mseries/install-touchid-settings.sh --revert"
