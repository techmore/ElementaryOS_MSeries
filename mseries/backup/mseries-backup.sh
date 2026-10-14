#!/usr/bin/env bash
# Pre-reinstall backup for the M1 Pro elementary OS 9 desktop.
# Writes a staging directory; nothing on the system is changed.
#   bash mseries/backup/mseries-backup.sh [staging-dir]
# Needs passwordless sudo for /etc and /boot. Secrets go to secrets.tar, which must only be copied to encrypted media.
set -uo pipefail
stamp=$(date +%Y%m%d-%H%M)
out=${1:-$HOME/backup-pre-reinstall-$stamp}
mkdir -p "$out"/{inventory,config,boot,git,home}
log() { printf '%s\n' "$*" | tee -a "$out/BACKUP-LOG.txt"; }
run() { local name=$1; shift; "$@" >"$out/inventory/$name" 2>&1 || true; }

log "backup started $(date -Is) on $(hostname) kernel $(uname -r)"

# --- inventory (text, small) ---
run uname.txt uname -a
run os-release.txt cat /etc/os-release
run dmi-model.txt bash -c 'cat /proc/device-tree/model; echo; cat /proc/device-tree/compatible | tr "\0" "\n"'
run lsblk.txt lsblk -o NAME,SIZE,TYPE,FSTYPE,UUID,PARTUUID,PARTTYPENAME,MOUNTPOINT,LABEL
run blkid.txt sudo blkid
run partition-table.txt bash -c 'sudo parted -m /dev/nvme0n1 unit s print; sudo parted /dev/nvme0n1 unit GiB print'
run asahi-nvram.txt bash -c 'sudo asahi-nvram list 2>&1; sudo asahi-bless --help 2>&1 | head -5'
run apfs-containers.txt bash -c 'lsblk -f /dev/nvme0n1; ls /dev/nvme0n*'
run fstab.txt cat /etc/fstab
run crypttab.txt sudo cat /etc/crypttab
run btrfs-subvolumes.txt sudo btrfs subvolume list /
run df.txt df -h
run dpkg-selections.txt dpkg --get-selections
run apt-manual.txt apt-mark showmanual
run dpkg-versions.txt dpkg-query -W -f='${Package} ${Version} ${Architecture}\n'
run apt-sources.txt bash -c 'cat /etc/apt/sources.list /etc/apt/sources.list.d/* 2>/dev/null; ls /etc/apt/preferences.d /etc/apt/trusted.gpg.d /etc/apt/keyrings 2>/dev/null'
run snap-list.txt snap list
run flatpak-list.txt flatpak list --columns=application,origin,installation,version
run flatpak-user-remotes.txt flatpak remotes --columns=name,url
run pip-user.txt python3 -m pip list --user
run cargo-bin.txt bash -c 'ls ~/.cargo/bin 2>/dev/null'
run go-bin.txt bash -c 'ls ~/go/bin 2>/dev/null'
run systemd-system-enabled.txt systemctl list-unit-files --state=enabled,masked,disabled --no-pager
run systemd-user-enabled.txt systemctl --user list-unit-files --state=enabled,masked --no-pager
run systemd-timers.txt systemctl list-timers --all --no-pager
run lsmod.txt lsmod
run modprobe-config.txt sudo modprobe --showconfig
run kernel-cmdline.txt cat /proc/cmdline
run dconf-dump.txt dconf dump /
run gsettings-pantheon.txt bash -c 'gsettings list-recursively | grep -E "elementary|pantheon|gala|wingpanel|plank|gnome.desktop.interface|gnome.desktop.peripherals" | sort'
run network-connections.txt nmcli -t -f NAME,TYPE,DEVICE,AUTOCONNECT connection show
run tailscale-status.txt tailscale status
run usb.txt lsusb -t
run audio-sinks.txt bash -c 'wpctl status; pactl list short sinks'
run power.txt bash -c 'cat /sys/class/power_supply/macsmc-battery/{charge_control_end_threshold,cycle_count,capacity} 2>&1; cat /sys/module/hid_apple/parameters/fnmode'
run crontabs.txt bash -c 'crontab -l 2>&1; sudo ls /etc/cron.d /etc/cron.daily 2>&1'
run hostnamectl.txt hostnamectl
run ip-addr.txt ip -br addr
run groups.txt id
run asahi-boot.txt bash -c 'ls -la /boot /boot/asahi /boot/m1n1 /boot/vendorfw /boot/grub 2>&1; which asahi-bless asahi-fwextract 2>&1; sudo cat /boot/grub/grub.cfg 2>&1 | head -200'
run kernel-packages.txt bash -c 'dpkg -l | grep -iE "linux-(image|headers|asahi|fairydust)|m1n1|u-boot|asahi|speakersafety|mesa" ; pacman -Q 2>/dev/null | head -0; ls /lib/modules'
run installed-mseries-files.txt bash -c 'ls -la ~/.local/bin ~/.local/libexec ~/.config/systemd/user /usr/local/bin /usr/local/lib/mseries /etc/systemd/system 2>&1'
log "inventory written"

# --- /etc, /boot, firmware (root) ---
sudo tar --xattrs --acls -czf "$out/config/etc.tar.gz" \
  --exclude=/etc/shadow --exclude=/etc/shadow- --exclude=/etc/gshadow --exclude=/etc/gshadow- \
  --exclude=/etc/ssh/ssh_host_* --exclude=/etc/NetworkManager/system-connections \
  --exclude=/etc/ssl/private --exclude=/etc/credstore --exclude=/etc/credstore.encrypted \
  /etc 2>>"$out/BACKUP-LOG.txt" && log "etc.tar.gz ok"
sudo tar --xattrs -czf "$out/boot/boot-vfat.tar.gz" /boot 2>>"$out/BACKUP-LOG.txt" && log "boot-vfat.tar.gz ok (includes Apple vendor firmware: do not redistribute)"
sudo tar -czf "$out/config/usr-local.tar.gz" /usr/local 2>>"$out/BACKUP-LOG.txt" && log "usr-local ok"
sudo tar -czf "$out/config/usr-lib-systemd-custom.tar.gz" /usr/lib/systemd/system-sleep /usr/lib/systemd/system/mseries* /usr/lib/systemd/system/omarchy* 2>/dev/null
sudo chown "$USER": "$out"/config/*.tar.gz "$out"/boot/*.tar.gz

# --- home (non-secret config and local code) ---
tar -czf "$out/home/dotfiles.tar.gz" -C "$HOME" \
  .bashrc .profile .inputrc .gitconfig .dmrc .bash_logout 2>/dev/null
tar -czf "$out/home/local-bin-libexec.tar.gz" -C "$HOME" --exclude='*.pyc' --exclude='.local/bin/signal-desktop' .local/bin .local/libexec .config/systemd/user .config/autostart .local/share/applications 2>/dev/null
tar -czf "$out/home/app-config.tar.gz" -C "$HOME" \
  --exclude='*/Cache*' --exclude='*/cache*' --exclude='*/GPUCache' --exclude='*/Code Cache' --exclude='*/logs' \
  --exclude='.config/Claude/scratch-workspaces' --exclude='.config/Claude/vm_bundles' \
  .config/mseries .config/dconf .config/io.elementary* .config/gtk-3.0 .config/gtk-4.0 .config/touchegg .config/git .config/pipewire .config/wireplumber \
  .config/Claude/claude_desktop_config.json .config/Claude/config.json \
  .claude/settings.json .claude/CLAUDE.md .claude/skills .claude/agents .claude/commands .claude/projects \
  .codex/config.toml .codex/AGENTS.md .codex/prompts .codex/skills .codex/rules .codex/memories \
  .config/opencode .local/share/opencode/*.json .opencode/*.json \
  .local/share/mseries-verify .local/state/mseries-troubleshooter .local/state/mseries-signal \
  .local/share/netusage .local/share/energy-monitor .local/share/CodexBar .local/share/crush .config/crush \
  .local/share/homeboard .local/share/nmapui .config/mseries .cache/mseries-upstream-watch.json \
  fairydust-build.sh fairydust-driver.sh mlx-backups Library 2>/dev/null
log "home config archives ok"

# --- secrets: copy only to encrypted media ---
sudo tar -cf "$out/secrets.tar" -C / --warning=no-file-changed \
  etc/NetworkManager/system-connections etc/ssh/ssh_host_* \
  "home/$USER/.ssh" "home/$USER/.gnupg" "home/$USER/.local/share/keyrings" "home/$USER/.claude.json" "home/$USER/.codex/auth.json" \
  var/lib/tailscale 2>/dev/null
sudo chown "$USER": "$out/secrets.tar"; chmod 600 "$out/secrets.tar"
log "secrets.tar written (Wi-Fi keys, SSH, GPG, keyrings, tokens, tailscale)"

# --- git: repos without a remote, plus uncommitted work in other people's forks ---
for d in "$HOME"/code/* "$HOME"/Documents/* "$HOME"/fairydust-usb4; do
  [ -d "$d/.git" ] || continue
  n=$(basename "$d"); r=$(git -C "$d" remote get-url origin 2>/dev/null || true)
  if [ -z "$r" ]; then git -C "$d" bundle create "$out/git/$n.bundle" --all >/dev/null 2>&1 && log "bundle: $n (no remote)"; fi
  if [ -n "$(git -C "$d" status --porcelain)" ]; then
    git -C "$d" diff HEAD > "$out/git/$n.uncommitted.diff" 2>/dev/null
    git -C "$d" status --porcelain | awk '$1=="??"{print $2}' | tar -czf "$out/git/$n.untracked.tar.gz" -C "$d" -T - 2>/dev/null
    log "dirty repo saved: $n"
  fi
  { echo "$n $r"; git -C "$d" rev-parse HEAD; git -C "$d" branch --show-current; } >> "$out/git/REPOS.txt" 2>/dev/null
done

# --- non-git documents worth keeping (small) ---
tar -czf "$out/home/documents-small.tar.gz" -C "$HOME/Documents" \
  --exclude='os9-*' --exclude='torrential-build-cache' --exclude='mesa-mlx-compute' --exclude='omarchy-mac-reference' --exclude='openbubbles-app' \
  --exclude='.git' --exclude='storage-recovery' --exclude='.venv' --exclude='node_modules' --exclude='*.AppImage' --exclude='*.zip' --exclude='build' --exclude='target' --exclude='*.iso' --exclude='*.img' --exclude='*.gguf' --exclude='*.safetensors' --exclude='__pycache__' \
  --exclude-vcs . 2>/dev/null
log "documents-small ok"
(cd "$out" && find . -type f ! -name SHA256SUMS -print0 | sort -z | xargs -0 sha256sum > SHA256SUMS)
log "backup finished $(date -Is); $(du -sh "$out" | cut -f1) total"
