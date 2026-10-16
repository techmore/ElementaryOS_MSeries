#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
runtime="$HOME/.local/share/mlx-omarchy/venv/bin/python"
launcher="$HOME/.local/bin/mlx-omarchy-serve"
if [[ ! -x $runtime && -x /usr/lib/omarchy-mlx/venv/bin/python ]]; then
  runtime=/usr/lib/omarchy-mlx/venv/bin/python
  launcher=/usr/bin/mlx-omarchy-serve
fi
test -x "$runtime" && test -x "$launcher" || { echo 'Install mseries/local-ai/install.sh first.' >&2; exit 1; }
"$runtime" - <<'PY'
from huggingface_hub import snapshot_download
snapshot_download('mlx-community/Qwen3.5-9B-MLX-4bit', revision='938d8919941c6e7efd3c7150eff7fe9d12afa631')
PY
test -f "$HOME/.config/systemd/user/mseries-ai-everyday.service" || { echo 'Run configure-assistants.py first.' >&2; exit 1; }
install -Dm755 "$repo/mseries/local-ai/troubleshoot.py" "$HOME/.local/bin/mseries-troubleshoot"
install -Dm755 "$repo/mseries/local-ai/brief.py" "$HOME/.local/bin/mseries-brief"
install -Dm755 "$repo/mseries/local-ai/ask.py" "$HOME/.local/bin/mseries-ask"
mkdir -p "$HOME/.config/systemd/user"
install -Dm755 "$repo/mseries/local-ai/troubleshooter-ui.py" "$HOME/.local/libexec/mseries-troubleshooter-ui"
install -Dm755 "$repo/mseries/local-ai/repair-panel.py" "$HOME/.local/libexec/mseries-repair-panel"
mkdir -p "$HOME/.local/share/applications"
cat > "$HOME/.local/share/applications/mseries-troubleshooter.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=Local Troubleshooter
Comment=Analyze crashes and logs privately with the shared local Qwen model
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
echo 'Optional 9B diagnosis needs 15 GiB available before loading; release it with: systemctl --user stop mseries-ai-quality'
