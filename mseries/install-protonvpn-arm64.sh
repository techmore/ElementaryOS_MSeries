#!/usr/bin/env bash
set -euo pipefail

if [[ "$(dpkg --print-architecture)" != arm64 ]]; then
  echo "This source build is for ARM64 Debian/Ubuntu systems." >&2
  exit 1
fi

for tool in flatpak-builder git; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Missing $tool. Install it with: sudo apt install $tool" >&2
    exit 1
  fi
done

if ! flatpak remotes --user --columns=name 2>/dev/null | grep -qx flathub &&
   ! flatpak remotes --system --columns=name 2>/dev/null | grep -qx flathub; then
  echo "Add the Flathub remote for this user before building Proton VPN." >&2
  echo "See https://flathub.org/setup" >&2
  exit 1
fi

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_dir="$(mktemp -d "${TMPDIR:-/tmp}/protonvpn-flathub.XXXXXX")"
trap 'rm -rf -- "$source_dir"' EXIT

# Pin the Flathub recipe so the local ARM64 build is reproducible.
flathub_recipe_commit=7387931c14c4d57763618d83644be19b3475c77c
git -C "$source_dir" init -q
git -C "$source_dir" remote add origin https://github.com/flathub/com.protonvpn.www.git
git -C "$source_dir" fetch --depth 1 origin "$flathub_recipe_commit"
git -C "$source_dir" checkout --detach FETCH_HEAD
git -C "$source_dir" submodule update --init --recursive

# GitLab's NetworkManager endpoint returned 502/504 during the validated build.
# Use the same 1.40.18 release archive from GNOME's mirror, pinned by SHA-256.
git -C "$source_dir" apply "$script_dir/protonvpn-arm64/flatpak-networkmanager-source.patch"

cache_base="${XDG_CACHE_HOME:-$HOME/.cache}"
mkdir -p "$cache_base/protonvpn-arm64-flatpak-builder"

flatpak-builder \
  --user \
  --install \
  --install-deps-from=flathub \
  --arch=aarch64 \
  --disable-updates \
  --delete-build-dirs \
  --state-dir "$cache_base/protonvpn-arm64-flatpak-builder" \
  -y \
  "$source_dir/build" \
  "$source_dir/com.protonvpn.www.yml"

echo "Installed Proton VPN for ARM64. Launch it from Applications or run: flatpak run com.protonvpn.www"
