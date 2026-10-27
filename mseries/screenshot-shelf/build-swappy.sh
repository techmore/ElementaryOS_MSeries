#!/usr/bin/env bash
# Build swappy v1.5.1 with the elementary additions (header-bar Close button,
# Print… with Ctrl+P, Save as PDF… with Ctrl+Shift+P) and install it for the
# current user only. No sudo. ~/.local/bin comes first in PATH, so it shadows
# the distro /usr/bin/swappy and `apt upgrade` of the swappy package cannot
# replace this behaviour; rerun this script to rebuild.
#   bash mseries/screenshot-shelf/build-swappy.sh [--prefix DIR]
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
prefix=$HOME/.local
if [[ ${1:-} == --prefix ]]; then prefix=${2:?--prefix needs a directory}; fi
repo=https://github.com/jtheoof/swappy.git
tag=v1.5.1
commit=a996b2cec65aadd04ded780f141b02c5bdfbeb32   # what tag v1.5.1 pointed to on 2026-10-27

for tool in git meson ninja gcc; do
  command -v "$tool" >/dev/null || { echo "missing build tool: $tool (sudo apt install git meson ninja-build gcc)" >&2; exit 1; }
done
pkg-config --exists gtk+-3.0 cairo pango || { echo "missing GTK3 development files (sudo apt install libgtk-3-dev)" >&2; exit 1; }

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
git clone -q --depth 1 --branch "$tag" "$repo" "$work/swappy"
[[ $(git -C "$work/swappy" rev-parse HEAD) == "$commit" ]] || { echo "tag $tag no longer points at $commit; refusing to build" >&2; exit 1; }
git -C "$work/swappy" apply "$here/swappy-print-close.patch"
meson setup "$work/build" "$work/swappy" -Dman-pages=disabled --prefix="$prefix" >/dev/null
ninja -C "$work/build" >/dev/null
mkdir -p "$prefix/bin"
install -m 0755 "$work/build/swappy" "$prefix/bin/swappy"
echo "installed $prefix/bin/swappy ($("$prefix/bin/swappy" --version))"
