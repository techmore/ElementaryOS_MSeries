#!/usr/bin/env bash
# Installs the vendored omdrop userspace (mseries/omdrop, from netmojo-systems/omdrop-plugin, MIT) for this user.
# No sudo, no systemd units enabled, and NO radio driver: omdrop-awdl replaces the running brcmfmac kernel driver,
# which is the kernel owner's decision. Without it AirDrop shows "Needs the Wi-Fi driver" and nothing listens.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dest="$HOME/.local/share/mseries-omdrop"
mkdir -p "$dest" "$HOME/.local/bin"
rm -rf "$dest/bin" "$dest/share"
cp -r "$repo/mseries/omdrop/bin" "$repo/mseries/omdrop/share" "$dest/"
cp "$repo/mseries/omdrop/manifest.json" "$repo/mseries/omdrop/README.md" "$repo/mseries/omdrop/LICENSE" "$repo/mseries/omdrop/PROVENANCE.md" "$dest/"
chmod +x "$dest/bin/omdrop"
ln -sfn "$dest/bin/omdrop" "$HOME/.local/bin/omdrop"
echo "Installed omdrop to $dest (command: ~/.local/bin/omdrop). The Wi-Fi radio driver is not installed."
