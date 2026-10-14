#!/usr/bin/env bash
# System tuning found by the 2026-10-12 audit. Idempotent; undo with --revert.
#
#   bash mseries/install-system-tuning.sh            # apply
#   bash mseries/install-system-tuning.sh --revert   # undo everything below
#
#  * zram swap (half of RAM, zstd): the machine had NO swap with ~19 GB in use, ~11 GB of it shared
#    (GPU) memory. Compressed swap in RAM is a safety net without disk wear.
#  * ModemManager disabled: this Mac has no modem.
#  * snap CUPS disabled: a second print stack running next to the apt CUPS (~50 MB).
#  * AppCenter's background daemon not autostarted: ~680 MB resident. AppCenter itself still works;
#    you just lose the automatic update check in the background.
set -euo pipefail

zram_conf=/etc/systemd/zram-generator.conf
sysctl_conf=/etc/sysctl.d/99-mseries-zram.conf
zswap_tmpfiles=/etc/tmpfiles.d/mseries-zswap.conf
autostart=$HOME/.config/autostart/io.elementary.appcenter.desktop

if [[ ${1:-} == --revert ]]; then
  systemctl stop systemd-zram-setup@zram0.service 2>/dev/null || sudo systemctl stop systemd-zram-setup@zram0.service || true
  sudo rm -f "$zram_conf" "$sysctl_conf" "$zswap_tmpfiles"
  sudo systemctl daemon-reload
  sudo systemctl enable --now ModemManager.service 2>/dev/null || true
  command -v snap >/dev/null && sudo snap start --enable cups 2>/dev/null || true
  rm -f "$autostart"
  echo 'Reverted. (systemd-zram-generator package left installed but unconfigured.)'
  exit 0
fi

# --- zram swap -------------------------------------------------------------------------------
dpkg -s systemd-zram-generator >/dev/null 2>&1 || sudo apt-get install -y systemd-zram-generator
sudo install -m 0644 /dev/stdin "$zram_conf" <<'EOF'
# ElementaryOS_MSeries: compressed swap in RAM
[zram0]
zram-size = ram / 2
max-zram-size = 8192
compression-algorithm = zstd
swap-priority = 100
EOF
sudo install -m 0644 /dev/stdin "$sysctl_conf" <<'EOF'
# ElementaryOS_MSeries: tuning for zram-backed swap (no disk seek cost, so swap eagerly, no read-ahead)
vm.swappiness = 100
vm.page-cluster = 0
EOF
sudo systemctl daemon-reload
sudo systemctl start systemd-zram-setup@zram0.service
sudo sysctl --system >/dev/null
# zswap would compress a second time on top of zram
if [[ -w /sys/module/zswap/parameters/enabled || $EUID -eq 0 ]] || sudo test -w /sys/module/zswap/parameters/enabled; then
  echo 0 | sudo tee /sys/module/zswap/parameters/enabled >/dev/null || true
fi
# ...and again after every boot (the sysfs write above is runtime-only).
sudo install -m 0644 /dev/stdin "$zswap_tmpfiles" <<'EOF'
# ElementaryOS_MSeries: zram already compresses swap
w /sys/module/zswap/parameters/enabled - - - - 0
EOF

# --- services that have no job on this machine -----------------------------------------------
sudo systemctl disable --now ModemManager.service
if command -v snap >/dev/null && snap list cups >/dev/null 2>&1; then
  sudo snap stop --disable cups
fi

# --- AppCenter background daemon ---------------------------------------------------------------
mkdir -p "$(dirname "$autostart")"
cat > "$autostart" <<'EOF'
[Desktop Entry]
Type=Application
Name=AppCenter (background updates disabled)
Hidden=true
EOF
pkill -f '^/usr/bin/io.elementary.appcenter --silent' 2>/dev/null || true   # anchored: cannot match this script's own command line

echo 'Done:'
swapon --show
