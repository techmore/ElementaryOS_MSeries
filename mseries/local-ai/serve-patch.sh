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
key=mlx-lm py=$prefix/venv/bin/python
# model-worker.py and engine-compare.py read the same folder. Never /tmp: RAM-backed.
out=${MSERIES_SERVE_PATCH_DIR:-$HOME/.local/share/mseries-ai/serve-patch}
# build-032 / check-032: the same patches ported to the mlx-lm 0.32 line in the oMLX venv
# (install-omlx.sh), for engine-compare's lm032-patched-120k arm only; the live server is untouched.
if [[ ${1:-build} == *-032 ]]; then
  key=mlx-lm-032 py=${MSERIES_OMLX_HOME:-$HOME/.local/share/omlx-linux}/.venvs/omlx/bin/python
  out=$HOME/.local/share/mseries-ai/serve-patch-032
  prefix=
fi
site=$("$py" -c 'import mlx_lm, os; print(os.path.dirname(mlx_lm.__file__))')
# upstreams.json is the one list of what we carry; upstream-step.py moves the pin and the files.
want=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upstreams"][sys.argv[2]]["pin"].lstrip("v"))' "$here/upstreams.json" "$key")
mapfile -t patches < <(python3 -c 'import json,sys
for p in json.load(open(sys.argv[1]))["upstreams"][sys.argv[3]]["patches"]: print(sys.argv[2] + "/" + p["file"])' "$here/upstreams.json" "$here" "$key")

case ${1:-build} in
  build|build-032)
    version=$("$py" -c 'import mlx_lm; print(mlx_lm.__version__)')
    # A release pin matches the version; a commit pin matches the dev version's +g<sha> suffix.
    [[ $version == "$want" || $version == *"g$want"* ]] || { echo "installed mlx-lm is $version; these patches are for $want" >&2; exit 2; }
    mkdir -p "$out"
    rm -rf "$out/mlx_lm.new"
    cp -a "$site" "$out/mlx_lm.new"
    find "$out/mlx_lm.new" -name __pycache__ -prune -exec rm -rf {} +
    cp "$here/serve_singleton_cache.py" "$out/mlx_lm.new/_mseries_singleton_cache.py"
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
  check|check-032)
    PYTHONPATH="${prefix:+$prefix:}$out" "$py" -c \
      'import importlib, mlx_lm.server as s; g = importlib.import_module("mlx_lm.generate")
print(s.__file__); print("skip-logprob-read:", hasattr(s, "_LOGPROB_READ_FORCED"))
print("singleton cache:", getattr(g, "_rapid_singleton_cache_fastpath", False))'
    ;;
  *) echo "usage: $0 build|check|build-032|check-032" >&2; exit 2 ;;
esac
