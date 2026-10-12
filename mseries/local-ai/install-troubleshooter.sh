#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
runtime="$HOME/.local/share/mlx-omarchy/venv/bin/python"
launcher="$HOME/.local/bin/mlx-omarchy-serve"
test -x "$runtime" && test -x "$launcher" || { echo 'Install mseries/local-ai/install.sh first.' >&2; exit 1; }
"$runtime" - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/gemma-4-e4b-it-4bit', revision='475b9088d29754a3379866cf5aeb6b41acd313c2')
PY
model="$HOME/.cache/huggingface/hub/models--mlx-community--gemma-4-e4b-it-4bit/snapshots/475b9088d29754a3379866cf5aeb6b41acd313c2"
install -Dm755 "$repo/mseries/local-ai/troubleshoot.py" "$HOME/.local/bin/mseries-troubleshoot"
mkdir -p "$HOME/.config/systemd/user"
cat > "$HOME/.config/systemd/user/mseries-troubleshooter-model.service" <<EOF
[Unit]
Description=On-device Gemma 4 troubleshooting model
[Service]
Environment=HF_HUB_OFFLINE=1
Environment=TRANSFORMERS_OFFLINE=1
Environment=HF_HUB_DISABLE_TELEMETRY=1
ExecStart="$launcher" serve "$model" --weights-gib 4.83 --context 4096 --host 127.0.0.1 --port 8767 --offline --yes
TimeoutStopSec=20
EOF
install -Dm755 "$repo/mseries/local-ai/troubleshooter-ui.py" "$HOME/.local/libexec/mseries-troubleshooter-ui"
install -Dm755 "$repo/mseries/local-ai/repair-panel.py" "$HOME/.local/libexec/mseries-repair-panel"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/mseries-troubleshooter.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Local Troubleshooter
Comment=Analyze crashes and logs privately with Gemma 4
Exec=/usr/bin/python3 "$HOME/.local/libexec/mseries-troubleshooter-ui"
Icon=utilities-system-monitor
Categories=System;Utility;
Terminal=false
EOF
systemctl --user daemon-reload
echo 'Installed. Run: mseries-troubleshoot --start "Why is my desktop crashing?"'
echo 'Release model memory with: systemctl --user stop mseries-troubleshooter-model'
