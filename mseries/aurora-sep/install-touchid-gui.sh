#!/usr/bin/env bash
# Install the Touch ID settings app for the current user.
#   bash mseries/aurora-sep/install-touchid-gui.sh              # install
#   bash mseries/aurora-sep/install-touchid-gui.sh --uninstall  # remove
#
# Needs: python3-gi (GTK3). The app talks to fprintd directly; the PAM button
# calls mseries-aurora-touchid-apply-pam through pkexec, which is installed
# to /usr/local/sbin with sudo.
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
here=$root
app=$here/mseries-touchid-settings
helper=$here/mseries-aurora-touchid-apply-pam
desktop_src=$here/mseries-touchid-settings.desktop
bin=$HOME/.local/bin
apps=$HOME/.local/share/applications

if [[ ${1:-} == --uninstall ]]; then
  rm -f "$bin/mseries-touchid-settings" "$bin/touchid_core.py" \
        "$apps/mseries-touchid-settings.desktop"
  sudo rm -f /usr/local/sbin/mseries-aurora-touchid-apply-pam
  update-desktop-database "$apps" 2>/dev/null || true
  echo "Removed Touch ID settings (enrolled fingerprints are kept)."
  exit 0
fi

dpkg -s python3-gi python3-gi-cairo >/dev/null 2>&1 || sudo apt-get install -y python3-gi python3-gi-cairo
mkdir -p "$bin" "$apps"
install -m 755 "$app" "$bin/mseries-touchid-settings"
install -m 644 "$here/touchid_core.py" "$bin/touchid_core.py"
install -m 644 "$desktop_src" "$apps/mseries-touchid-settings.desktop"
sudo install -m 755 "$helper" /usr/local/sbin/mseries-aurora-touchid-apply-pam
update-desktop-database "$apps" 2>/dev/null || true
echo "Installed. Launch 'Touch ID (M-series)' from the applications menu, or run:"
echo "  mseries-touchid-settings"
