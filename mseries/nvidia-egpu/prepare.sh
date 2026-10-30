#!/usr/bin/env bash
# Prepare NVIDIA's 595.112.07 open modules plus the public 16K fixes; never install.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
out=${1:?usage: prepare.sh NEW_OUTPUT_DIRECTORY}
[[ ! -e $out ]] || { echo 'Output already exists' >&2; exit 1; }
mkdir -p "$out"
git -C "$out" init -q
git -C "$out" fetch -q --depth 1 https://github.com/NVIDIA/open-gpu-kernel-modules.git d8257d95ae5fed364163e4df51db66df8b1ee0d2
git -C "$out" checkout -q --detach FETCH_HEAD
[[ $(git -C "$out" rev-parse HEAD) == d8257d95ae5fed364163e4df51db66df8b1ee0d2 ]]
(cd "$here/patches" && sha256sum -c SHA256SUMS)
for patch in 0001-16k-system-page.patch 0002-arm64-dma-submap.patch; do
  git -C "$out" apply --check "$here/patches/$patch"
  git -C "$out" apply "$here/patches/$patch"
done
printf '%s\n' 'Prepared NVIDIA open modules 595.112.07 with PRs 1480 and 1481; no build or installation.'
