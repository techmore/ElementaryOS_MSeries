#!/bin/bash
# First-boot bring-up on Gravity Linux (Fedora 44, M4 Mac mini J773g).
# Run as your normal user (uses sudo). Gets network, remote access, Claude Code
# and this repo onto the machine, then stops before building elementary.
#   bash gravity-bringup.sh [--ssh-key 'ssh-ed25519 AAAA...'] [--wifi SSID]
set -euo pipefail

ssh_key="" wifi=""
while (( $# )); do
  case $1 in
    --ssh-key) ssh_key=${2:?--ssh-key needs a public key}; shift ;;
    --wifi) wifi=${2:?--wifi needs an SSID}; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
  shift
done

log() { printf '\033[32m==>\033[0m %s\n' "$*"; }

[[ $(uname -m) == "aarch64" ]] || { echo "aarch64 only" >&2; exit 1; }
grep -qx 'ID=fedora' /etc/os-release || { echo "this is for the Gravity (Fedora) image" >&2; exit 1; }

if ! curl -fsS --max-time 8 -o /dev/null https://github.com; then
  if [[ -n $wifi ]]; then
    log "Joining Wi-Fi $wifi (nmcli asks for the password)"
    sudo nmcli --ask device wifi connect "$wifi"
  else
    echo "No network. Join Wi-Fi first: nmcli device wifi list; sudo nmcli --ask device wifi connect <SSID>" >&2
    exit 1
  fi
fi

log "Installing tools"
sudo dnf install -y git gh btrfs-progs pciutils curl tar xz zstd openssh-server

if [[ -n $ssh_key ]]; then
  [[ $ssh_key =~ ^(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+)\ [A-Za-z0-9+/=]+(\ .*)?$ ]] || { echo "not a public key" >&2; exit 1; }
  log "Enabling key-only SSH"
  install -d -m 700 ~/.ssh
  grep -qxF "$ssh_key" ~/.ssh/authorized_keys 2>/dev/null || printf '%s\n' "$ssh_key" >>~/.ssh/authorized_keys
  chmod 600 ~/.ssh/authorized_keys
  printf 'PasswordAuthentication no\nKbdInteractiveAuthentication no\nPermitRootLogin no\n' | sudo tee /etc/ssh/sshd_config.d/10-mseries.conf >/dev/null
  sudo systemctl enable --now sshd
fi

log "Installing Claude Code (Anthropic's installer)"
curl -fsSL https://claude.ai/install.sh | bash

log "Fetching the elementary M-series repo"
[[ -d ~/ElementaryOS_MSeries ]] || gh repo clone techmore/ElementaryOS_MSeries ~/ElementaryOS_MSeries -- --branch prep/m4-mini-aurora-installer 2>/dev/null || git clone --branch prep/m4-mini-aurora-installer https://github.com/techmore/ElementaryOS_MSeries ~/ElementaryOS_MSeries

cat <<'NEXT'

Ready. Start Claude Code with:   cd ~/ElementaryOS_MSeries && claude
Check the host first:            sudo ELEMENTARY_HOST=fedora bash transform/elementary-grow.sh --dry-run
Then build elementary:           sudo ELEMENTARY_HOST=fedora ELEMENTARY_ENHANCE=1 bash transform/elementary-grow.sh --apply
Create your account:             sudo ELEMENTARY_HOST=fedora ELEMENTARY_PASSWORD_HASH="$(openssl passwd -6)" bash transform/elementary-grow.sh --finalize <user>
Pick "elementary OS (M-series)" in the boot menu. Rollback: --rollback.
NEXT
