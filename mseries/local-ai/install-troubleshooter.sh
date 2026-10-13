#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
runtime="$HOME/.local/share/mlx-omarchy/venv/bin/python"
launcher="$HOME/.local/bin/mlx-omarchy-serve"
test -x "$runtime" && test -x "$launcher" || { echo 'Install mseries/local-ai/install.sh first.' >&2; exit 1; }
"$runtime" - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/Qwen3.5-9B-4bit', revision='8b2b98c00a6b4d291155e4890773ca8f769aee53')
PY
model="$HOME/.cache/huggingface/hub/models--mlx-community--Qwen3.5-9B-4bit/snapshots/8b2b98c00a6b4d291155e4890773ca8f769aee53"
install -Dm755 "$repo/mseries/local-ai/troubleshoot.py" "$HOME/.local/bin/mseries-troubleshoot"
install -Dm755 "$repo/mseries/local-ai/brief.py" "$HOME/.local/bin/mseries-brief"
install -Dm755 "$repo/mseries/local-ai/ask.py" "$HOME/.local/bin/mseries-ask"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/mseries-troubleshooter-model.service" <<EOF
[Unit]
Description=On-device Qwen3.5-9B troubleshooting model
[Service]
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=HF_HUB_DISABLE_TELEMETRY=1
ExecStart="$launcher" serve "$model" --weights-gib 5.57 --context 4096 --host 127.0.0.1 --port 8767 --offline --yes
TimeoutStopSec=20
SuccessExitStatus=143
EOF
install -Dm755 "$repo/mseries/local-ai/troubleshooter-ui.py" "$HOME/.local/libexec/mseries-troubleshooter-ui"
install -Dm755 "$repo/mseries/local-ai/repair-panel.py" "$HOME/.local/libexec/mseries-repair-panel"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/mseries-troubleshooter.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Local Troubleshooter
Comment=Analyze crashes and logs privately with Qwen3.5-9B
Exec=/usr/bin/python3 "$HOME/.local/libexec/mseries-troubleshooter-ui"
Icon=utilities-system-monitor
Categories=System;Utility;
Terminal=false
Actions=Performance;

[Desktop Action Performance]
Name=Check Native Performance
Exec=/usr/bin/python3 "$HOME/.local/libexec/mseries-troubleshooter-ui" --performance
EOF
systemctl --user daemon-reload
echo 'Installed. Run: mseries-troubleshoot --start "Why is my desktop crashing?"'
echo 'Release model memory with: systemctl --user stop mseries-troubleshooter-model'
