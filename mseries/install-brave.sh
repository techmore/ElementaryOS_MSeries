#!/usr/bin/env bash
# Brave browser from Brave's own apt repository (arm64).
#   bash mseries/install-brave.sh              # install
#   bash mseries/install-brave.sh --uninstall  # remove Brave and the repository
# The keyring is only trusted if every key in it is one of Brave's published release keys.
set -euo pipefail
source "$(dirname -- "${BASH_SOURCE[0]}")/lib-apt.sh"
allowed=(DBF1A116C220B8C7164F98230686B78420038257
         47D32A74E9A9E013A4B4926C68D513D36A73CD96
         B2A3DCA350E67256740DF904DE4EC67BE4B0DCA0)
keyring=/usr/share/keyrings/brave-browser-archive-keyring.gpg
source_file=/etc/apt/sources.list.d/brave-browser-release.sources

if [[ ${1:-} == --uninstall ]]; then
  sudo apt-get remove -y brave-browser || true
  sudo rm -f "$source_file" "$keyring"
  mseries_apt_refresh
  echo 'Removed.'
  exit 0
fi

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -fsS https://brave-browser-apt-release.s3.brave.com/brave-browser-archive-keyring.gpg -o "$tmp/key.gpg"
mapfile -t found < <(gpg --show-keys --with-colons "$tmp/key.gpg" | awk -F: '$1=="pub"{want=1; next} $1=="fpr" && want {print $10; want=0}')
(( ${#found[@]} > 0 )) || { echo 'No keys found in the downloaded keyring' >&2; exit 1; }
for fpr in "${found[@]}"; do
  [[ " ${allowed[*]} " == *" $fpr "* ]] || { echo "Unexpected signing key $fpr" >&2; exit 1; }
done

sudo install -D -m 0644 "$tmp/key.gpg" "$keyring"
sudo tee "$source_file" >/dev/null <<SRC
Types: deb
URIs: https://brave-browser-apt-release.s3.brave.com
Suites: stable
Components: main
Architectures: arm64
Signed-By: $keyring
SRC
mseries_apt_refresh
sudo apt-get install -y brave-browser
dpkg-query -W -f='Brave ${Version} (${Status})\n' brave-browser
