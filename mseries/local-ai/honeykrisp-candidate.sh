#!/usr/bin/env bash
# Build one pinned Honeykrisp (joshuaswarren/mesa-1) commit beside the installed
# private driver, with install.sh's exact Mesa flags. Nothing installed changes:
# the result is selected per process with MSERIES_HK_ICD=<printed path>.
#
#   honeykrisp-candidate.sh <full-40-char-commit>
#
# Why: coreglass's daily ledger shows its newer stack (driver 9323171c12, MLX main)
# decoding faster on an M1 than the release stack we run (driver e7631595df);
# our pin 7faf04c065 is older than both. Known risk: f144c7949b (6 commits before
# 9323171c12) crashes agx_ra on software cooperative matrices with AGX_SIMDMAT=1;
# see receipts/2026-10-19-honeykrisp-v3-candidate. The MLX gate decides.
set -euo pipefail

rev=${1:?usage: $0 <full commit sha>}
[[ $rev =~ ^[0-9a-f]{40}$ ]] || { echo "give the full 40-character commit" >&2; exit 2; }
root=${MSERIES_HK_ROOT:-$HOME/.cache/mseries-honeykrisp}   # never /tmp: RAM-backed
src=$root/src-${rev:0:10}
prefix=$root/${rev:0:10}
free=$(df --output=avail -BG "$HOME" | tail -1 | tr -dc 0-9)
(( free >= 5 )) || { echo "refusing: ${free} GiB free under \$HOME, floor is 5" >&2; exit 1; }

if [[ ! -d $src/.git ]]; then
  git init -q "$src"
  git -C "$src" remote add origin https://github.com/joshuaswarren/mesa-1.git
fi
if [[ $(git -C "$src" rev-parse -q --verify HEAD 2>/dev/null) != "$rev" ]]; then
  git -C "$src" fetch -q --depth 1 origin "$rev"
  git -C "$src" checkout -q --detach FETCH_HEAD
fi
[[ $(git -C "$src" rev-parse HEAD) == "$rev" ]] || { echo "checkout is not $rev" >&2; exit 1; }

meson setup --reconfigure "$src/build-mlx" "$src" --prefix="$src/private" --libdir=lib \
  -Dgallium-drivers= -Dvulkan-drivers=asahi -Dplatforms= -Dglx=disabled \
  -Degl=disabled -Dgbm=disabled -Dgles1=disabled -Dgles2=disabled \
  -Dopengl=false -Dllvm=enabled -Dbuildtype=release
ninja -C "$src/build-mlx" -j "${MSERIES_AI_JOBS:-4}"
meson install -C "$src/build-mlx" >/dev/null

mkdir -p "$prefix/vulkan"
install -m755 "$src/private/lib/libvulkan_asahi.so" "$prefix/vulkan/"
python3 -I - "$src/private/share/vulkan/icd.d/asahi_icd.aarch64.json" "$prefix" <<'PY'
import json, sys
from pathlib import Path
source, prefix = Path(sys.argv[1]), Path(sys.argv[2])
if not source.exists():
    source = next(source.parent.glob('*asahi*.json'))
data = json.loads(source.read_text())
data['ICD']['library_path'] = str(prefix / 'vulkan/libvulkan_asahi.so')
(prefix / 'vulkan/honeykrisp_icd.aarch64.json').write_text(json.dumps(data, indent=2) + '\n')
PY
printf '%s\n' "$(git -C "$src" rev-parse --short=10 HEAD)" > "$prefix/vulkan/mesa-git-sha"

icd=$prefix/vulkan/honeykrisp_icd.aarch64.json
VK_DRIVER_FILES=$icd vulkaninfo --summary 2>/dev/null | grep -E "deviceName|driverInfo" | head -2
echo "MSERIES_HK_ICD=$icd"
