#!/bin/bash
# Install upstream Linux ARM64 desktop + CLI; no fork required.
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
version=v0.74.1
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
for component in CLI Desktop; do
  archive="CodexBar${component}-${version}-linux-aarch64.tar.gz"
  base="https://github.com/steipete/CodexBar/releases/download/${version}"
  curl -fLsS "$base/$archive" -o "$archive"
  curl -fLsS "$base/$archive.sha256" -o "$archive.sha256"
  sha256sum -c "$archive.sha256"
done
mkdir -p "$HOME/.local/lib/codexbar-cli" "$HOME/.local/bin"
tar -xzf "CodexBarCLI-${version}-linux-aarch64.tar.gz" -C "$HOME/.local/lib/codexbar-cli"
ln -sfn "$HOME/.local/lib/codexbar-cli/codexbar" "$HOME/.local/bin/codexbar"
tar -xzf "CodexBarDesktop-${version}-linux-aarch64.tar.gz"
cd "CodexBarDesktop-${version}-linux-aarch64"
python3 Integrations/Linux/install.py --cli "$HOME/.local/bin/codexbar"
echo 'Open ~/.local/bin/codexbar-linux --settings. Runtime dependencies: see mseries/DESKTOP-SETUP.md.'
