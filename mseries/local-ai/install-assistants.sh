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
  sudo apt-get install -y flatpak gir1.2-ecal-2.0 gir1.2-edataserver-1.2 gir1.2-gtk-3.0 python3-websockets
fi
flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo
flatpak install --user --assumeyes --noninteractive flathub io.github.qwersyk.Newelle
flatpak update --user --assumeyes --noninteractive --commit=7f106d29dc4fd3ee032005fe4160da8996b889a6b8e62db0ee7e9ab185561fa1 io.github.qwersyk.Newelle
python3 "$here/mark-newelle-chat.py"  # Smart Reply chat-app marker; harmless while Smart Reply is off
"$runtime" - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/Qwen3.5-9B-MLX-4bit',revision='938d8919941c6e7efd3c7150eff7fe9d12afa631',max_workers=2)
# Smart Reply drafting model (reply-model-compare.md).
snapshot_download('mlx-community/Qwen3.5-4B-MLX-4bit',revision='32f3e8ecf65426fc3306969496342d504bfa13f3',max_workers=2)
PY
python3 "$here/prepare-compact35.py"
python3 "$here/install-crush.py"
python3 "$here/prepare-coder.py" --python "$runtime" --runtime-only
python3 "$here/configure-assistants.py" --adopt-compact-defaults
bash "$here/install-troubleshooter.sh"
install -Dm755 "$here/crash-watch.py" "$HOME/.local/libexec/mseries-crash-watch"
install -Dm755 "$here/reply-modeld.py" "$HOME/.local/libexec/mseries-ai/reply-modeld.py"
install -Dm644 "$here/mseries-reply-model.service" "$HOME/.config/systemd/user/mseries-reply-model.service"
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
# Smart Reply's 8766 endpoint now loads on demand instead of keeping the everyday model resident.
systemctl --user disable --now mseries-ai-everyday.service 2>/dev/null || true
systemctl --user enable --now mseries-reply-model.service
echo 'Installed assistant profiles and fault watcher. Quiet policy may refuse a model when desktop headroom is short.'
