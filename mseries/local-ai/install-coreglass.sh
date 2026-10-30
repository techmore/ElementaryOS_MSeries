#!/usr/bin/env bash
# Coreglass alone (GPU/ANE benchmark viewer), at our pin with our patch, without rebuilding the
# MLX runtime the way install.sh does. Same source folder as install.sh, so either can update it.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
read -r pin < <(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["upstreams"]["coreglass"]["pin"])' "$here/upstreams.json")
src=${MSERIES_AI_SOURCES:-$HOME/.local/share/mseries-ai/sources/v0.7.35}/coreglass
if [[ ! -d $src/.git ]]; then
  git init -q "$src"
  git -C "$src" remote add origin https://github.com/joshuaswarren/coreglass.git
fi
if [[ $(git -C "$src" rev-parse HEAD 2>/dev/null) != "$pin" ]]; then
  [[ -z $(git -C "$src" status --porcelain --untracked-files=no 2>/dev/null) ]] || git -C "$src" checkout -q -- .
  git -C "$src" fetch -q --depth 1 origin "$pin"
  git -C "$src" checkout -q --detach FETCH_HEAD
fi
if git -C "$src" apply --check "$here/coreglass-local.patch" 2>/dev/null; then
  git -C "$src" apply "$here/coreglass-local.patch"
else
  git -C "$src" apply -R --check "$here/coreglass-local.patch"  # already applied
fi
python3 -m venv "$src/.venv"
"$src/.venv/bin/pip" install -q "$src"
"$src/.venv/bin/coreglass" install
mkdir -p "$HOME/.local/bin"
ln -sfn "$src/.venv/bin/coreglass" "$HOME/.local/bin/coreglass"
echo "coreglass $(git -C "$src" rev-parse --short HEAD) + coreglass-local.patch -> $HOME/.local/bin/coreglass"
