#!/usr/bin/env bash
# Native (non-snap) Firefox from Mozilla's own apt repository, arm64.
#   bash mseries/install-native-firefox.sh              # install
#   bash mseries/install-native-firefox.sh --uninstall  # remove Firefox and the repository
# Ubuntu's "firefox" package is a snap shim; snaps start slowly and sandbox GPU access poorly. The pin below
# makes apt prefer Mozilla's package. The signing key is checked against Mozilla's published fingerprint.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib-apt.sh"
fingerprint=35BAA0B33E9EB396F59CA838C0BA5CE6DC6315A3
keyring=/etc/apt/keyrings/packages.mozilla.org.asc

if [[ ${1:-} == --uninstall ]]; then
  sudo apt-get remove -y firefox || true
  sudo rm -f /etc/apt/sources.list.d/mozilla.sources /etc/apt/preferences.d/mozilla "$keyring"
  mseries_apt_refresh
  echo 'Removed.'
  exit 0
fi

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -fsS https://packages.mozilla.org/apt/repo-signing-key.gpg -o "$tmp/key.gpg"
actual=$(gpg --show-keys --with-colons "$tmp/key.gpg" | awk -F: '$1=="fpr"{print $10; exit}')
[[ $actual == "$fingerprint" ]] || { echo "Signing key fingerprint mismatch: $actual" >&2; exit 1; }

sudo install -d -m 0755 /etc/apt/keyrings
gpg --dearmor < "$tmp/key.gpg" | sudo tee "${keyring%.asc}.gpg" >/dev/null
sudo tee /etc/apt/sources.list.d/mozilla.sources >/dev/null <<SRC
Types: deb
URIs: https://packages.mozilla.org/apt
Suites: mozilla
Components: main
Architectures: arm64
Signed-By: ${keyring%.asc}.gpg
SRC
sudo tee /etc/apt/preferences.d/mozilla >/dev/null <<'PIN'
Package: *
Pin: origin packages.mozilla.org
Pin-Priority: 1000
PIN
mseries_apt_refresh
sudo apt-get install -y firefox
dpkg-query -W -f='Firefox ${Version} (${Status})\n' firefox
