#!/usr/bin/env bash
# oMLX for engine-compare.py's omlx-120k arm, the way omarchy-mlx packages it for Linux
# (packaging/omlx-linux at our omarchy-mlx pin): its own venv and HOME under
# ~/.local/share/omlx-linux, on the mlx-omarchy wheel from the same release. The live MLX
# runtime and services are not touched. Test engine only, not a default.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
read -r pin label < <(python3 -c 'import json,sys; u=json.load(open(sys.argv[1]))["upstreams"]["omarchy-mlx"]; print(u["pin"], u["pin_label"])' "$here/upstreams.json")
cache=$HOME/.cache/mseries-omlx   # never /tmp: RAM-backed here
home=${MSERIES_OMLX_HOME:-$HOME/.local/share/omlx-linux}
mkdir -p "$cache/wheel"
if [[ ! -d $cache/omarchy-mlx/.git ]]; then
  git init -q "$cache/omarchy-mlx"
  git -C "$cache/omarchy-mlx" remote add origin https://github.com/joshuaswarren/omarchy-mlx.git
fi
git -C "$cache/omarchy-mlx" fetch -q --depth 1 origin "$pin"
git -C "$cache/omarchy-mlx" checkout -q --force --detach FETCH_HEAD
wheel_glob="mlx_omarchy-*-cp314-cp314-linux_aarch64.whl"
gh release download "$label" -R joshuaswarren/omarchy-mlx -D "$cache/wheel" --clobber -p "$wheel_glob" -p SHA256SUMS
(cd "$cache/wheel" && grep -E " \*?mlx_omarchy-.*-cp314-cp314-linux_aarch64\.whl$" SHA256SUMS | sha256sum -c -)
wheel=$(ls "$cache/wheel"/$wheel_glob)
bash "$cache/omarchy-mlx/packaging/omlx-linux/install.sh" --mlx-wheel "$wheel" --home "$home" \
  --omlx-dir "$cache/omlx"
"$home/.venvs/omlx/bin/omlx" --version
echo "Next: python3 $here/engine-compare.py --model qwen2b --arms serve-patched-120k,rapid-120k,omlx-120k"
