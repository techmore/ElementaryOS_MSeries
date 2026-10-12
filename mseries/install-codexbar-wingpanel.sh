#!/bin/bash
# Build and install the Pantheon-native CodexBar Wingpanel indicator.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/codexbar-wingpanel"

if [[ ${1:-} == --uninstall ]]; then
  indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)
  sudo rm -f "$indicators_dir/libcodexbar.so"
  echo 'Removed the CodexBar Wingpanel indicator. Log out and back in to reload Wingpanel.'
  exit 0
fi

for tool in meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo '  sudo apt install meson ninja-build valac libwingpanel-9-dev libgranite-7-dev libjson-glib-dev' >&2
    exit 1
  }
done

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/codexbar-wingpanel.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
meson setup "$build_dir" "$src" --prefix=/usr
ninja -C "$build_dir"
sudo ninja -C "$build_dir" install
echo 'Installed CodexBar in Wingpanel. Log out and back in; the panel indicator starts the CodexBar backend and displays remaining quota.'
