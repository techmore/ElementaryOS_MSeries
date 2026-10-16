#!/usr/bin/env bash
# Battery charge limit (default 80%), plus a lower CPU ceiling and power-saver profile on battery.
#   bash mseries/install-power.sh              # install and apply now
#   bash mseries/install-power.sh --uninstall  # remove, restore 100% and full CPU speed
# Change the limit later with: sudo mseries-power limit 100|80. Policy file: /etc/mseries/power.conf
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

if [[ ${1:-} == --uninstall ]]; then
  sudo mseries-power limit 100 >/dev/null || true
  sudo sh -c 'for p in /sys/devices/system/cpu/cpufreq/policy*; do cat "$p/cpuinfo_max_freq" > "$p/scaling_max_freq"; done'
  sudo systemctl disable --now mseries-power.service mseries-power-follow.service 2>/dev/null || true
  sudo rm -f /usr/share/polkit-1/actions/org.techmore.mseries.power.policy /usr/local/sbin/mseries-power /etc/systemd/system/mseries-power.service /etc/systemd/system/mseries-power-follow.service /etc/udev/rules.d/80-mseries-power.rules /etc/mseries/power.conf
  sudo udevadm control --reload; sudo systemctl daemon-reload
  echo 'Removed; charge limit back to 100% and CPU ceiling lifted.'
  exit 0
fi

sudo install -Dm755 "$repo/mseries/power/mseries-power" /usr/local/sbin/mseries-power
# Lets the Quick Settings charge-limit switch run `mseries-power limit` after an admin password prompt.
sudo install -Dm644 "$repo/mseries/power/org.techmore.mseries.power.policy" /usr/share/polkit-1/actions/org.techmore.mseries.power.policy
sudo tee /etc/systemd/system/mseries-power.service >/dev/null <<'UNIT'
[Unit]
Description=Apply battery charge limit and power-source CPU policy
After=power-profiles-daemon.service

[Service]
Type=oneshot
ExecStart=/usr/local/sbin/mseries-power apply

[Install]
WantedBy=graphical.target
UNIT
# Lifts the battery CPU ceiling while the balanced profile is active (a burst) and restores it in power-saver.
sudo tee /etc/systemd/system/mseries-power-follow.service >/dev/null <<'UNIT'
[Unit]
Description=Re-apply the battery CPU ceiling when the power profile changes
After=power-profiles-daemon.service

[Service]
ExecStart=/usr/local/sbin/mseries-power follow
Restart=on-failure

[Install]
WantedBy=graphical.target
UNIT
sudo tee /etc/udev/rules.d/80-mseries-power.rules >/dev/null <<'RULE'
# Plugging or unplugging the charger re-applies the policy.
SUBSYSTEM=="power_supply", KERNEL=="macsmc-ac", ACTION=="change", TAG+="systemd", ENV{SYSTEMD_WANTS}+="mseries-power.service"
RULE
sudo udevadm control --reload
sudo systemctl daemon-reload
sudo systemctl enable --now mseries-power.service mseries-power-follow.service
mseries-power status
