#!/usr/bin/env bash
# Package the prepared NVIDIA source kit only; no module is built or loaded.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
src=${1:?usage: package-source.sh PREPARED_SOURCE NEW_OUTPUT_DEB}
out=${2:?usage: package-source.sh PREPARED_SOURCE NEW_OUTPUT_DEB}
[[ ! -e $out ]] || { echo 'Refusing to overwrite output' >&2; exit 1; }
[[ $(git -C "$src" rev-parse HEAD) == d8257d95ae5fed364163e4df51db66df8b1ee0d2 ]] || { echo 'Unexpected NVIDIA source revision' >&2; exit 1; }
(cd "$here/patches" && sha256sum -c SHA256SUMS)
[[ -z $(git -C "$src" ls-files --others --exclude-standard) ]] || { echo "Untracked files in source" >&2; exit 1; }
[[ $(git -C "$src" diff --binary | sha256sum | cut -d" " -f1) == 6bdbb8493e7c14c5ca9e62ff7547aca075923759718bd233a2bbecbf1f489943 ]] || { echo "Unexpected source changes" >&2; exit 1; }
for patch in 0001-16k-system-page.patch 0002-arm64-dma-submap.patch 0003-apple-tunnel-595.patch; do
  git -C "$src" apply --reverse --check "$here/patches/$patch"
done
work=$(mktemp -d "${TMPDIR:-/tmp}/mseries-nvidia-source.XXXXXXXX")
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/DEBIAN" "$work/usr/src/mseries-nvidia-open-595.112.07" "$work/usr/share/doc/mseries-nvidia-open-source"
tar -C "$src" --exclude=.git -cf - . | tar -C "$work/usr/src/mseries-nvidia-open-595.112.07" -xf -
cp "$src/COPYING" "$work/usr/share/doc/mseries-nvidia-open-source/copyright"
cp "$here/README.md" "$work/usr/share/doc/mseries-nvidia-open-source/README"
cat > "$work/DEBIAN/control" <<'CONTROL'
Package: mseries-nvidia-open-source
Version: 595.112.07+apple.1-1
Architecture: all
Maintainer: ElementaryOS MSeries contributors <builder@localhost>
Section: kernel
Priority: optional
Description: NVIDIA open GPU module source with Apple Silicon fixes
 Prepared source only; requires matching kernel build tree and NVIDIA userspace.
CONTROL
dpkg-deb --root-owner-group --build "$work" "$out"
