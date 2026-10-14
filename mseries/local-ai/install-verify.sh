#!/usr/bin/env bash
# Install mseries-verify: the pending-checks list with SQLite history, run by a user timer.
#
#   bash mseries/local-ai/install-verify.sh              # install + start the timer
#   bash mseries/local-ai/install-verify.sh --uninstall  # remove the timer and tool (keeps verify.db history)
#
# Day to day:  mseries-verify status | run --notify | confirm ID yes|no | history [ID]
# Data:        ~/.local/state/mseries-troubleshooter/verify.db (+ verify-status.json for the panel/UI)
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
unit_dir=$HOME/.config/systemd/user

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-verify.timer 2>/dev/null || true
  rm -f "$unit_dir/mseries-verify.timer" "$unit_dir/mseries-verify.service" "$HOME/.local/bin/mseries-verify"
  systemctl --user daemon-reload
  echo 'Removed the timer and tool. Recorded results stay in ~/.local/state/mseries-troubleshooter/verify.db.'
  exit 0
fi

install -Dm755 "$repo/mseries/local-ai/verify.py" "$HOME/.local/bin/mseries-verify"
install -Dm644 "$repo/mseries/local-ai/verify-checks.json" "$HOME/.local/share/mseries-verify/checks.json"
install -Dm755 "$repo/mseries/local-ai/upstream-watch.py" "$HOME/.local/share/mseries-verify/upstream-watch.py"
install -Dm755 "$repo/mseries/local-ai/touchid-watch.py" "$HOME/.local/share/mseries-verify/touchid-watch.py"
install -Dm755 "$repo/mseries/local-ai/people-watch.py" "$HOME/.local/share/mseries-verify/people-watch.py"
install -Dm644 "$repo/mseries/local-ai/people-watch.json" "$HOME/.local/share/mseries-verify/people-watch.json"
# The troubleshooter window shows open checks, if it is installed.
if [[ -f $HOME/.local/libexec/mseries-troubleshooter-ui ]]; then
  install -Dm755 "$repo/mseries/netspeed/troubleshooter/mseries-troubleshooter-ui" "$HOME/.local/libexec/mseries-troubleshooter-ui"
fi

mkdir -p "$unit_dir"
cat > "$unit_dir/mseries-verify.service" <<'EOF'
[Unit]
Description=Run pending Mac verification checks

[Service]
Type=oneshot
ExecStart=%h/.local/bin/mseries-verify run --notify --quiet
Nice=10
EOF
cat > "$unit_dir/mseries-verify.timer" <<'EOF'
[Unit]
Description=Run pending Mac verification checks after login and every 10 minutes

[Timer]
OnStartupSec=90s
OnUnitActiveSec=10min
AccuracySec=30s

[Install]
WantedBy=timers.target
EOF

"$HOME/.local/bin/mseries-verify" reload
systemctl --user daemon-reload
systemctl --user enable --now mseries-verify.timer
echo 'Installed. Current state:'
"$HOME/.local/bin/mseries-verify" run --notify
"$HOME/.local/bin/mseries-verify" status
