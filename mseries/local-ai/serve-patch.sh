#!/usr/bin/env bash
# Private mlx-lm server patches for the everyday model, tested beside the installed runtime.
#
#   serve-patch.sh build    copy the installed mlx_lm into the patch folder and apply our
#                           patches there (the installed venv is not touched)
#   serve-patch.sh check    show which mlx_lm the launcher would import with the copy first
#
# engine-compare.py's serve-nolp-120k engine puts the copy first on PYTHONPATH, so the same
# upstream launcher (mlx-omarchy-serve: memory reservation, speech yield gate, context cap)
# runs the patched server. Why: upstream's server copies the sampled token's logprob back
# from the GPU on every token even when no request asked for it; on Honeykrisp that is a
# full GPU wait per token. omarchy-mlx fixed this on its mlx-lm 0.32 line only.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
prefix=${OMARCHY_MLX_SYSTEM_PREFIX:-$HOME/.local/share/mlx-omarchy}
# model-worker.py and engine-compare.py read the same folder. Never /tmp: RAM-backed.
out=${MSERIES_SERVE_PATCH_DIR:-$HOME/.local/share/mseries-ai/serve-patch}
site=$(ls -d "$prefix"/venv/lib/python3.*/site-packages/mlx_lm | head -n1)
# upstreams.json is the one list of what we carry; upstream-step.py moves the pin and the files.
want=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upstreams"]["mlx-lm"]["pin"].lstrip("v"))' "$here/upstreams.json")
mapfile -t patches < <(python3 -c 'import json,sys
for p in json.load(open(sys.argv[1]))["upstreams"]["mlx-lm"]["patches"]: print(sys.argv[2] + "/" + p["file"])' "$here/upstreams.json" "$here")
# Modules a patch imports (serve_X.py ships as mlx_lm/_mseries_X.py).
mapfile -t extras < <(python3 -c 'import json,sys
for p in json.load(open(sys.argv[1]))["upstreams"]["mlx-lm"]["patches"]:
    for f in p.get("extra_files", []): print(f)' "$here/upstreams.json")

case ${1:-build} in
  build)
    version=$("$prefix/venv/bin/python" -c 'import mlx_lm; print(mlx_lm.__version__)')
    [[ $version == "$want" ]] || { echo "installed mlx-lm is $version; these patches are for $want" >&2; exit 2; }
    mkdir -p "$out"
    rm -rf "$out/mlx_lm.new"
    cp -a "$site" "$out/mlx_lm.new"
    find "$out/mlx_lm.new" -name __pycache__ -prune -exec rm -rf {} +
    for f in "${extras[@]}"; do
      cp "$here/$f" "$out/mlx_lm.new/_mseries_${f#serve_}"
    done
    for p in "${patches[@]}"; do
      # The labels say mlx_lm/; -d into the copy and strip that one component.
      patch -s -p2 -d "$out/mlx_lm.new" --dry-run -i "$p" >/dev/null
      patch -s -p2 -d "$out/mlx_lm.new" -i "$p"
      echo "applied $(basename "$p")"
    done
    rm -rf "$out/mlx_lm"
    mv "$out/mlx_lm.new" "$out/mlx_lm"
    # model-worker.py uses the copy only while the installed server.py still has this hash, so
    # an omarchy-mlx upgrade can never be shadowed by a stale copy.
    sha256sum "$site/server.py" | cut -d' ' -f1 > "$out/source-server-sha256"
    echo "MSERIES_SERVE_PATCH_DIR=$out"
    ;;
  check)
    PYTHONPATH="$prefix:$out" "$prefix/venv/bin/python" -c \
      'import importlib, mlx_lm.server as s; g = importlib.import_module("mlx_lm.generate")
print(s.__file__); print("skip-logprob-read:", hasattr(s, "_LOGPROB_READ_FORCED"))
print("singleton cache:", getattr(g, "_rapid_singleton_cache_fastpath", False))
import mlx.nn as nn; print("small rows:", getattr(nn.QuantizedLinear, "_mseries_small_rows", False))'
    ;;
  *) echo "usage: $0 build|check" >&2; exit 2 ;;
esac
