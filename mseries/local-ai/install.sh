#!/usr/bin/env bash
# elementary ARM64: private MLX compute driver, runtime and Coreglass.
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'Requires ARM64 Apple Silicon' >&2; exit 1; }
grep -aq 'apple,' /proc/device-tree/compatible || { echo 'Requires Apple Silicon' >&2; exit 1; }
python3 -c 'import sys; assert sys.version_info[:2] == (3,14), "Python 3.14 required"'
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=${MSERIES_AI_SOURCES:-$HOME/.local/share/mseries-ai/sources/v0.7.33}
prefix=$HOME/.local/share/mlx-omarchy
mkdir -p "$work"
# The upstream installer clears its venv. Never replace a running worker.
if pgrep -u "$(id -u)" -f "$prefix/venv/bin/python" >/dev/null; then
  echo 'Stop MLX chat/model workers before updating the runtime.' >&2; exit 1
fi
backup=
if [[ -e $prefix ]]; then
  backup=${prefix}.before-v0.7.33-$(date +%s)
  mv "$prefix" "$backup"
fi
installer=
rollback() {
  local rc=$?
  [[ -z $installer ]] || rm -f "$installer"
  if (( rc != 0 )) && [[ -n $backup ]]; then
    [[ ! -e $prefix ]] || mv "$prefix" "${prefix}.failed-$(date +%s)"
    mv "$backup" "$prefix"
    echo 'Restored the previous MLX runtime after the failed update.' >&2
  fi
}
trap rollback EXIT
sudo apt-get install -y git curl build-essential meson ninja-build pkg-config python3-venv \
  libopenblas0 liblapack3 vulkan-tools llvm-21-dev libclang-21-dev clang-21 \
  libclc-21-dev libclc-21 libllvmspirvlib-21-dev spirv-tools spirv-tools-dev \
  libdrm-dev libelf-dev libexpat1-dev libzstd-dev libudev-dev libvulkan-dev \
  glslang-tools rustc bindgen cbindgen python3-mako python3-ply python3-yaml
checkout() {
  local name=$1 repo=$2 pin=$3
  if [[ ! -d $work/$name/.git ]]; then
    git init "$work/$name"
    git -C "$work/$name" remote add origin "https://github.com/joshuaswarren/$repo.git"
    git -C "$work/$name" fetch --depth 1 origin "$pin"
    git -C "$work/$name" checkout --detach FETCH_HEAD
  fi
  [[ $(git -C "$work/$name" rev-parse HEAD) == "$pin" ]] || {
    echo "Unexpected source revision in $work/$name; use a separate MSERIES_AI_SOURCES directory." >&2; exit 1;
  }
  if [[ $name == coreglass ]] && cmp -s <(git -C "$work/$name" diff) "$script_dir/coreglass-local.patch"; then
    return
  fi
  [[ -z $(git -C "$work/$name" status --porcelain --untracked-files=no) ]] || {
    echo "Tracked changes in $work/$name; refusing to build a modified source." >&2; exit 1;
  }
}
checkout coreglass coreglass 25603cbf1f95fd2819b11d914afec58997ef1b8b
checkout omarchy-mlx omarchy-mlx 33630f9c1eeefe5fc985a28bed0585432c2c014e
# 9323171c12 (2026-10-25): identical MLX gate results to 7faf04c065 and faster decode on the
# M1 Pro (Qwen 2B +36%, Qwen 4B +24%, LFM3 +48% at defaults); see ENGINE-SCOREBOARD.md.
checkout mesa-mlx-compute mesa-1 9323171c12c5aa6055f1031ea26c16c247191987
if git -C "$work/coreglass" apply --check "$script_dir/coreglass-local.patch" 2>/dev/null; then
  git -C "$work/coreglass" apply "$script_dir/coreglass-local.patch"
else
  git -C "$work/coreglass" apply -R --check "$script_dir/coreglass-local.patch"
fi
python3 -m venv "$work/coreglass/.venv"
"$work/coreglass/.venv/bin/pip" install "$work/coreglass"
"$work/coreglass/.venv/bin/coreglass" install
mkdir -p "$HOME/.local/bin"
ln -sfn "$work/coreglass/.venv/bin/coreglass" "$HOME/.local/bin/coreglass"
mesa=$work/mesa-mlx-compute
meson setup --reconfigure "$mesa/build-mlx" "$mesa" --prefix="$mesa/private" --libdir=lib \
  -Dgallium-drivers= -Dvulkan-drivers=asahi -Dplatforms= -Dglx=disabled \
  -Degl=disabled -Dgbm=disabled -Dgles1=disabled -Dgles2=disabled \
  -Dopengl=false -Dllvm=enabled -Dbuildtype=release
ninja -C "$mesa/build-mlx" -j "${MSERIES_AI_JOBS:-2}"
meson install -C "$mesa/build-mlx"
mkdir -p "$prefix/vulkan"
install -m755 "$mesa/private/lib/libvulkan_asahi.so" "$prefix/vulkan/"
python3 - "$mesa/private/share/vulkan/icd.d/asahi_icd.aarch64.json" "$prefix" <<'PY'
import json,sys
from pathlib import Path
source,prefix=Path(sys.argv[1]),Path(sys.argv[2])
# Mesa versions differ in the generated ICD basename.
if not source.exists(): source=next(source.parent.glob('*asahi*.json'))
data=json.loads(source.read_text())
data['ICD']['library_path']=str(prefix/'vulkan/libvulkan_asahi.so')
(prefix/'vulkan/honeykrisp_icd.aarch64.json').write_text(json.dumps(data,indent=2)+'\n')
PY
# Mesa reports its abbreviated git identity; pin exactly that identity.
printf '%s\n' "$(git -C "$mesa" rev-parse --short=10 HEAD)" > "$prefix/vulkan/mesa-git-sha"
installer=$(mktemp)
python3 - "$work/omarchy-mlx" "$installer" <<'PY'
from pathlib import Path
import sys
root=Path(sys.argv[1]); text=(root/'install.sh').read_text()
start=text.index('say "Installing runtime packages'); end=text.index('# Voice playback',start)
text=text[:start]+'say "Ubuntu runtime packages installed by elementary wrapper"\n'+text[end:]
old='ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"'
assert old in text
text=text.replace(old,'ROOT="'+str(root)+'"',1)
Path(sys.argv[2]).write_text(text)
PY
export OMARCHY_MLX_SYSTEM_PREFIX=$prefix
MLX_OMARCHY_VERSION=v0.7.33 bash "$installer"
python3 "$script_dir/configure-prefill.py" "$prefix/mlx_omarchy_serve/__main__.py"
# Keep driver selection local to MLX launchers; never set global Vulkan variables.
python3 - "$HOME/.local/bin" <<'PY'
from pathlib import Path
import sys
for path in Path(sys.argv[1]).glob('mlx-omarchy*'):
    if not path.is_file(): continue
    text=path.read_text()
    line='export OMARCHY_MLX_SYSTEM_PREFIX="$HOME/.local/share/mlx-omarchy"\n'
    if line not in text: path.write_text(text.replace('\n','\n'+line,1))
PY
python3 - <<'CONFIG'
from pathlib import Path
p=Path.home()/'.config/coreglass/hosts.toml'
p.parent.mkdir(parents=True,exist_ok=True)
text=p.read_text() if p.exists() else ''
if '[local]' not in text:
    prefix=Path.home()/'.local/share/mlx-omarchy'
    text+=f'\n[local]\nssh = "local"\nchip = "Apple Silicon"\ngpu_lock = "/tmp/mseries-ai-gpu.lock"\nmlx_python = "{prefix}/venv/bin/python"\nenv = {{ OMARCHY_MLX_SYSTEM_PREFIX = "{prefix}" }}\n'
    p.write_text(text)
CONFIG
"$HOME/.local/bin/mlx-omarchy-info"
echo 'Installed Coreglass and MLX Chat. Model downloads are selected in MLX Chat.'
[[ -z $backup ]] || echo "Previous runtime retained at $backup"
