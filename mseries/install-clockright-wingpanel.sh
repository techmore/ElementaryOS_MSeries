#!/bin/bash
# Install a right-side Wingpanel date/time while the centered notch area is being fixed.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/clockright"
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9)

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f "$indicators_dir/libclockright.so"
  echo 'Removed the right-side date/time indicator. Log out and back in to reload Wingpanel.'
  exit 0
fi

for tool in meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo '  sudo apt install meson ninja-build valac libwingpanel-9-dev' >&2
    exit 1
  }
done

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/clockright-wingpanel.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
meson setup "$build_dir" "$src" --prefix=/usr
ninja -C "$build_dir"
sudo ninja -C "$build_dir" install
echo 'Installed the right-side Wingpanel date/time. Log out and back in to load it.'
