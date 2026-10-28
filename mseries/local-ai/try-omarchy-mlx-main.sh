#!/usr/bin/env bash
# Try an unreleased omarchy-mlx commit without touching the installed runtime.
#
#   try-omarchy-mlx-main.sh [COMMIT]      default: the commit already checked out in ~/.cache/mseries-omx-main/src
#
# 1. builds upstream's release wheel from that commit (scripts/build-wheel.sh, 4 jobs);
# 2. copies the installed venv to ~/.cache/mseries-omx-main/venv and swaps in the new wheel;
# 3. runs the MLX correctness gate (mlx-gate.py, Qwen 2B vs the cached CPU reference) on both venvs;
# 4. times Smart Reply's model (reply-model-compare.py, Qwen3.5-4B) on both venvs.
# Results land in ~/.cache/mseries-omx-main/results/. Nothing under ~/.local is changed.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../.." && pwd)
root=$HOME/.cache/mseries-omx-main
src=$root/src
live=$HOME/.local/share/mlx-omarchy/venv
side=$root/venv
out=$root/results
qwen4b=$HOME/.cache/huggingface/hub/models--mlx-community--Qwen3.5-4B-MLX-4bit/snapshots/32f3e8ecf65426fc3306969496342d504bfa13f3
bundle=$live/lib/python3.14/site-packages/mlx/share/mlx-omarchy/parakeet-1/bundles/parakeet-encoder-whole

if [[ ! -d $src/.git ]]; then
  git init -q "$src"
  git -C "$src" remote add origin https://github.com/joshuaswarren/omarchy-mlx.git
fi
if [[ -n ${1:-} ]]; then
  git -C "$src" fetch -q --depth 1 origin "$1"
  git -C "$src" checkout -q --detach FETCH_HEAD
fi
commit=$(git -C "$src" rev-parse HEAD)
[[ -z $(git -C "$src" status --porcelain --untracked-files=no) ]] || { echo "Tracked changes in $src" >&2; exit 1; }
free_gib=$(( $(df --output=avail -k "$root" | tail -1) / 1024 / 1024 ))
(( free_gib >= 4 )) || { echo "Only ${free_gib} GiB free; the build and side venv need about 4." >&2; exit 1; }
mkdir -p "$out"
echo "== omarchy-mlx $commit"

echo "== 1/4 build wheel (log: $root/build.log)"
rm -rf "$src/dist"
( cd "$src" && MLX_OMARCHY_WHOLE_BUNDLE_DIR=$bundle CMAKE_BUILD_PARALLEL_LEVEL=${JOBS:-4} DEV_RELEASE=1 \
    nice -n 10 ./scripts/build-wheel.sh ) > "$root/build.log" 2>&1 || { tail -30 "$root/build.log"; exit 1; }
wheel=$(ls "$src"/dist/mlx_omarchy-*.whl)
echo "   $wheel"

echo "== 2/4 side venv"
rm -rf "$side"
cp -a "$live" "$side"
"$side/bin/python" -m pip install -q --no-deps --force-reinstall "$wheel"
# The build tree is no longer needed; give the disk back.
rm -rf "$src/.work"
"$side/bin/python" -c 'import mlx.core as mx, importlib.metadata as m; print("   side:", m.version("mlx_omarchy"))'
"$live/bin/python" -c 'import importlib.metadata as m; print("   live:", m.version("mlx_omarchy"))'

export OMARCHY_MLX_SYSTEM_PREFIX=$HOME/.local/share/mlx-omarchy PYTHONPATH=$HOME/.local/share/mlx-omarchy \
  VK_DRIVER_FILES=$HOME/.local/share/mlx-omarchy/vulkan/honeykrisp_icd.aarch64.json HF_HUB_OFFLINE=1 \
  MLX_OMARCHY_BATCH_WORK=120000
for name in live side; do
  py=$live/bin/python; [[ $name == side ]] && py=$side/bin/python
  echo "== 3/4 correctness gate: $name"
  MSERIES_MLX_PYTHON=$py python3 "$here/mlx-gate.py" sweep --configs work120k --admission-wait-seconds 120 \
    --output "$out/gate-$name.json" > "$out/gate-$name.txt" 2>&1 || true
  tail -6 "$out/gate-$name.txt"
  echo "== 4/4 Smart Reply timing: $name"
  for round in 1 2; do
    "$py" "$here/reply-model-compare.py" "$qwen4b" --repo "$repo" > "$out/reply-$name-$round.jsonl" 2>/dev/null
    tail -1 "$out/reply-$name-$round.jsonl"
  done
done
echo "== done: results in $out (side venv kept at $side for installing)"
