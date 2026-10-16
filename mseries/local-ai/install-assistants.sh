#!/usr/bin/env bash
# Reproduce the M1 Pro local assistant installation. Models download explicitly here.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
[[ $(uname -m) == aarch64 ]] || { echo 'Requires Apple Silicon Linux ARM64.' >&2; exit 1; }
grep -aq 'apple,t6000' /proc/device-tree/compatible || { echo 'This profile targets M1 Pro/T6000.' >&2; exit 1; }
if [[ ${1:-} == --runtime ]]; then
  bash "$here/install.sh"
  exit
fi
if [[ -x /usr/lib/omarchy-mlx/venv/bin/python ]]; then
  runtime=/usr/lib/omarchy-mlx/venv/bin/python
  # Factory dependencies are baked; setup never writes immutable /usr.
else
  test -x "$HOME/.local/bin/mlx-omarchy-serve" || bash "$here/install.sh"
  runtime="$HOME/.local/share/mlx-omarchy/venv/bin/python"
  sudo apt-get install -y flatpak gir1.2-ecal-2.0 gir1.2-edataserver-1.2
fi
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user --assumeyes --noninteractive flathub io.github.qwersyk.Newelle
flatpak update --user --assumeyes --noninteractive --commit=7f106d29dc4fd3ee032005fe4160da8996b889a6b8e62db0ee7e9ab185561fa1 io.github.qwersyk.Newelle
"$runtime" - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/Qwen3.5-9B-MLX-4bit',revision='938d8919941c6e7efd3c7150eff7fe9d12afa631',max_workers=2)
snapshot_download('mlx-community/Qwen3-4B-Instruct-2507-4bit',revision='50d427756c6b1b2fe0c0a10f67fbda1fc8e82c1b',max_workers=2)
PY
base="$HOME/.local/share/mseries-assistants/hermes"
pin=848fc0ad8be766b9dc10fe42bd80b5fc2d45d95c
if [[ ! -d $base/source/.git ]]; then
  mkdir -p "$base/source"
  git -C "$base/source" init
  git -C "$base/source" remote add origin https://github.com/NousResearch/hermes-agent.git
  git -C "$base/source" fetch --depth 1 origin "$pin"
  git -C "$base/source" checkout --detach FETCH_HEAD
fi
[[ $(git -C "$base/source" rev-parse HEAD) == "$pin" ]] || { echo 'Unexpected Hermes source revision; retained unchanged.' >&2; exit 1; }
[[ -z $(git -C "$base/source" status --porcelain --untracked-files=no) ]] || { echo 'Hermes source has tracked changes.' >&2; exit 1; }
python3 -m venv "$base/venv"
"$base/venv/bin/pip" install -r "$here/hermes-requirements.lock"
"$base/venv/bin/pip" install --no-deps -e "$base/source[mcp]"
python3 "$here/install-crush.py"
python3 "$here/prepare-coder.py" --python "$runtime" --runtime-only
python3 "$here/configure-assistants.py"
bash "$here/install-troubleshooter.sh"
install -Dm755 "$here/crash-watch.py" "$HOME/.local/libexec/mseries-crash-watch"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/mseries-crash-watch.service" <<'EOF'
[Unit]
Description=Watch local application and kernel faults
[Service]
ExecStart=/usr/bin/python3 %h/.local/libexec/mseries-crash-watch
Restart=on-failure
RestartSec=10
Nice=10
[Install]
WantedBy=default.target
EOF
systemctl --user daemon-reload
# Migrate the earlier MLX resident-pair login worker before enabling this one.
# Leave an unrelated/custom command using that unit name untouched.
legacy=$(systemctl --user show mlx-omarchy-chat.service -p ExecStart --value 2>/dev/null || true)
if [[ $legacy == *'/mlx-omarchy-chat '* ]]; then
  systemctl --user disable --now mlx-omarchy-chat.service
fi
systemctl --user enable --now mseries-crash-watch.service
systemctl --user enable --now mseries-ai-everyday.service
echo 'Installed assistant profiles and fault watcher. Quiet policy may refuse a model when desktop headroom is short.'
