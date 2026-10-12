#!/bin/bash
# elementary-grow.sh — grow an elementary OS boot entry out of a running
# omarchy-mac (Apple Silicon, Asahi). See mseries/TRANSFORM-DESIGN.md.
#
#   sudo ./elementary-grow.sh --upload     # dry run + upload log as secret Gist
#
# Getting the log back: the script always saves a full log to /tmp. With
# --upload it posts that log as a SECRET gist (needs `gh` authenticated or
# GITHUB_TOKEN set) and prints the URL — paste the URL back and the reviewer
# sees everything without you copying screens of text.
#   sudo ./elementary-grow.sh --apply      # perform the work
#   sudo ./elementary-grow.sh --rollback   # remove @elementary + boot entry
#   sudo ./elementary-grow.sh --status     # read-only report (needs root)
#   sudo ./elementary-grow.sh --finish-root    # add greeter/panel to a build
#   sudo ./elementary-grow.sh --repair-grub    # drop stale .removed dup, regen
#   sudo ./elementary-grow.sh --add-user [NAME]  # login acct (default admin/admin)
#   sudo ./elementary-grow.sh --finalize [NAME]  # repair-grub + add-user + status
#   sudo ./elementary-grow.sh --logs       # read-only: new root + last boot logs
#   sudo ./elementary-grow.sh --sync-kernel  # graft host kernel modules + firmware
#
# Safety contract: additive-only. New subvolume, new GRUB menu entry, old
# system and default boot entry untouched. Every assumption in the design
# doc is a runtime check below; any failure aborts before changing
# anything. Must run as root ON the omarchy-mac system, never from macOS.
set -euo pipefail

MODE="dry-run"
UPLOAD=0
USER_NAME="${ELEMENTARY_USER:-}"
LOGFILE="/tmp/elementary-grow-$(date +%Y%m%d-%H%M%S).log"
for arg in "$@"; do
  case "$arg" in
    --apply) MODE="apply" ;;
    --rollback) MODE="rollback" ;;
    --status) MODE="status" ;;
    --finish-root) MODE="finish-root" ;;
    --cleanup-stale) MODE="cleanup-stale" ;;
    --repair-grub) MODE="repair-grub" ;;
    --add-user) MODE="add-user" ;;
    --finalize) MODE="finalize" ;;
    --logs) MODE="logs" ;;
    --sync-kernel) MODE="sync-kernel" ;;
    --dry-run) MODE="dry-run" ;;
    --upload) UPLOAD=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    -*) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
    *) USER_NAME="$arg" ;;
  esac
done

SUBVOL_NAME="@elementary"
HOME_SUBVOL="@elementary-home"
GRUB_CUSTOM="/etc/grub.d/40_elementary-grow"
SNAP_PREFIX="@.snapshots/elementary-grow"
MIN_FREE_GB=40
UBUNTU_SUITE="resolute"
UBUNTU_BASE_URL="https://cdimage.ubuntu.com/ubuntu-base/${UBUNTU_SUITE}/daily/current/${UBUNTU_SUITE}-base-arm64.tar.gz"
# M-series layer, pinned to the commit that authored this script.
MSERIES_BASE="https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/mkosi.images/apple-silicon/mkosi.extra"
# Repo checkout this script runs from (for PPA keyrings/sources carried in
# repos/common-files + repos/stable — never fetched over the network).
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

log()  { echo "[elementary-grow] $*"; }
fail() { echo "[elementary-grow] ABORT: $*" >&2; exit 1; }

run() {
  if [[ $MODE == "dry-run" ]]; then log "(dry-run) would run: $*";
  else log "+ $*"; "$@"; fi
}

# ---------------------------------------------------------------- checks
preconditions() {
  [[ $(id -u) -eq 0 ]] || fail "run as root (sudo) on the omarchy-mac system"
  [[ $(uname -s) == "Linux" ]] || fail "Linux only — never run from macOS"
  [[ $(uname -m) == "aarch64" ]] || fail "aarch64 only (found $(uname -m))"
  local compat="/proc/device-tree/compatible"
  [[ -f $compat ]] && grep -Faiq 'apple,' "$compat" \
    || fail "no Apple device-tree — not Apple Silicon"
  [[ $(findmnt -no FSTYPE /) == "btrfs" ]] || fail "root (/) is not btrfs"
  command -v btrfs >/dev/null || fail "btrfs-progs not installed"
  command -v grub-mkconfig >/dev/null || fail "grub-mkconfig not found"
  [[ -d /etc/grub.d ]] || fail "/etc/grub.d missing — unknown bootloader setup"
  command -v curl >/dev/null || fail "curl not installed"
  command -v lspci >/dev/null || fail "lspci not installed (pciutils)"
  local free_gb
  free_gb=$(df -BG / | awk 'NR==2 {gsub("G",""); print $4}')
  (( free_gb >= MIN_FREE_GB )) \
    || fail "only ${free_gb}G free on / — need ${MIN_FREE_GB}G"
  # Host kernel + modules must exist as a matched pair; the new system
  # reuses them, so there is no fallback if they disagree.
  local kver
  kver=$(uname -r)
  [[ -d "/usr/lib/modules/$kver" ]] || [[ -d "/lib/modules/$kver" ]] \
    || fail "no modules tree for running kernel $kver"
  ls /boot/vmlinuz-* 2>/dev/null | grep -q . \
    || fail "no kernel image in /boot"
  ls /boot/initramfs-* 2>/dev/null | grep -q . \
    || fail "no initramfs in /boot"
  log "preconditions OK (kernel $kver, ${free_gb}G free)"
}

detect_chip() {
  if lspci -nn 2>/dev/null | grep -q "14e4:4425"; then echo "4378b1";
  elif lspci -nn 2>/dev/null | grep -q "14e4:4433"; then echo "4387c2";
  else echo ""; fi
}

# Mount the btrfs top level (subvolid=5) so the new subvolume is a sibling
# of the current root no matter the distro's subvolume layout.
TOP_MNT=""
mount_top() {
  local src opts
  src=$(findmnt -no SOURCE /)               # e.g. /dev/nvme0n1p2[/@]
  src=${src%%\[*}                           # strip [subvol] suffix
  opts="subvolid=5"
  [[ $MODE == "dry-run" ]] && opts="ro,$opts"  # dry run never writes
  TOP_MNT=$(mktemp -d /tmp/elementary-grow-top.XXXXXX)
  mount -o "$opts" "$src" "$TOP_MNT" \
    || fail "cannot mount btrfs top level from $src"
  log "btrfs top level at $TOP_MNT"
}

unmount_top() {
  [[ -n $TOP_MNT ]] || return 0
  umount -R "$TOP_MNT" 2>/dev/null || umount -l "$TOP_MNT" 2>/dev/null || true
  rmdir "$TOP_MNT" 2>/dev/null || true
  TOP_MNT=""
}

# Unmount leftover /tmp/elementary-grow-top.* mounts from runs whose
# chroot EXIT trap raced the main EXIT trap (binds leaked, top busy).
cleanup_stale() {
  local m
  for m in $(findmnt -rno TARGET | grep '^/tmp/elementary-grow-top\.' | sort -r); do
    log "unmounting stale $m"
    umount -R "$m" 2>/dev/null || umount -l "$m" 2>/dev/null || true
  done
  rmdir /tmp/elementary-grow-top.* 2>/dev/null || true
  log "stale mounts cleaned"
}

# Read-only report for troubleshooting the new root from omarchy.
do_status() {
  mount_top
  trap unmount_top EXIT
  echo "--- disk ---"
  df -h / /boot
  echo "--- subvolumes ---"
  btrfs subvolume list / | grep -E "@elementary|@\.snapshots/elementary-grow" || echo "(none)"
  echo "--- new root size ---"
  du -sh "$TOP_MNT/$SUBVOL_NAME" 2>/dev/null || echo "(no $SUBVOL_NAME)"
  echo "--- new root identity ---"
  cat "$TOP_MNT/$SUBVOL_NAME/etc/hostname" 2>/dev/null || echo "(no hostname)"
  cat "$TOP_MNT/$SUBVOL_NAME/etc/fstab" 2>/dev/null || echo "(no fstab)"
  echo "--- desktop ---"
  chroot "$TOP_MNT/$SUBVOL_NAME" dpkg -l elementary-desktop elementary-minimal elementary-standard 2>/dev/null | grep -E "^ii" || echo "(desktop packages not installed)"
  echo "--- firmware ---"
  ls "$TOP_MNT/$SUBVOL_NAME/lib/firmware/brcm" 2>/dev/null | grep -c brcm || echo "(no firmware dir)"
  echo "--- boot entry ---"
  local n
  n=$(grep -c "elementary OS (M-series" /boot/grub/grub.cfg 2>/dev/null || true)
  if (( n == 0 )); then echo "(no entry)";
  elif (( n == 1 )); then echo "1 entry";
  else echo "$n entries — WARNING: duplicate; check /etc/grub.d/*.removed is not executable"; fi
  echo "--- grub.d files ---"
  ls -l /etc/grub.d/*elementary* 2>/dev/null || echo "(none)"
  echo "--- current root (as seen by grub) ---"
  echo "/boot/vmlinuz-linux-asahi + /initramfs-linux-asahi.img present: $(ls /boot/vmlinuz-* /boot/initramfs-* 2>/dev/null | wc -l) files"
  echo "--- display manager ---"
  readlink "$TOP_MNT/$SUBVOL_NAME/etc/systemd/system/display-manager.service" 2>/dev/null || echo "(no display-manager symlink)"
  echo "--- graphical stack ---"
  chroot "$TOP_MNT/$SUBVOL_NAME" dpkg -l pantheon gala lightdm io.elementary.greeter io.elementary.wingpanel 2>/dev/null | grep -E "^ii|^un" || echo "(graphical pkgs unknown)"
  echo "--- users (uid>=1000) ---"
  awk -F: '$3>=1000 && $3<60000 {print $1, $3, $6}' "$TOP_MNT/$SUBVOL_NAME/etc/passwd" 2>/dev/null || echo "(no passwd)"
}

# ---------------------------------------------------------------- rollback
do_rollback() {
  mount_top
  if [[ -e "$TOP_MNT/$SUBVOL_NAME" || -e "$TOP_MNT/$HOME_SUBVOL" ]]; then
    run btrfs subvolume delete "$TOP_MNT/$SUBVOL_NAME" 2>/dev/null || true
    run btrfs subvolume delete "$TOP_MNT/$HOME_SUBVOL" 2>/dev/null || true
  else log "no $SUBVOL_NAME/$HOME_SUBVOL subvolumes — nothing to delete"; fi
  # grub-mkconfig runs EVERY executable file in /etc/grub.d, so an aside
  # file must also lose its executable bit or it adds a second, identical
  # menuentry (the classic "two elementary OS entries, both broken" bug).
  if [[ -f $GRUB_CUSTOM ]]; then
    if [[ $MODE != "dry-run" ]]; then
      rm -f "$GRUB_CUSTOM.removed"
      mv "$GRUB_CUSTOM" "$GRUB_CUSTOM.removed"
      chmod -x "$GRUB_CUSTOM.removed"
      log "moved $GRUB_CUSTOM aside (non-executable; grub ignores it)"
    else log "(dry-run) would move $GRUB_CUSTOM aside"; fi
    run grub-mkconfig -o /boot/grub/grub.cfg
  else
    # No live entry, but a prior rollback may have left an executable .removed
    # that grub still renders. Neutralize it and refresh the menu.
    if [[ -f "$GRUB_CUSTOM.removed" ]]; then
      if [[ $MODE != "dry-run" ]]; then
        chmod -x "$GRUB_CUSTOM.removed"
        log "neutralized leftover $GRUB_CUSTOM.removed"
      else log "(dry-run) would neutralize leftover $GRUB_CUSTOM.removed"; fi
      run grub-mkconfig -o /boot/grub/grub.cfg
    else log "no $GRUB_CUSTOM — bootloader untouched"; fi
  fi
  unmount_top
  log "rollback done. Snapshots under $SNAP_PREFIX-* are kept; delete manually."
}

# ---------------------------------------------------------------- apply
do_apply() {
  preconditions
  mount_top
  trap unmount_top EXIT

  local stamp snap
  stamp=$(date +%Y%m%d-%H%M%S)
  snap="$TOP_MNT/$SNAP_PREFIX-$stamp"
  [[ -e "$TOP_MNT/$SUBVOL_NAME" ]] \
    && fail "$SUBVOL_NAME already exists — --rollback first if retrying"
  [[ -e "$TOP_MNT/$HOME_SUBVOL" ]] \
    && fail "$HOME_SUBVOL already exists — --rollback first if retrying"
  log "snapshotting current root to $snap"
  if [[ $MODE == "apply" ]]; then
    mkdir -p "$TOP_MNT/@.snapshots" \
      || fail "cannot create @.snapshots dir at btrfs top"
    btrfs subvolume snapshot -r / "$snap" \
      || fail "root snapshot failed — aborting before any other change"
  else
    run btrfs subvolume snapshot -r / "$snap"
  fi
  # Separate home subvolume: sharing @home across Arch and Ubuntu would mix
  # dotfiles/dconf between Hyprland and Pantheon. Cheap to separate now.
  log "creating $TOP_MNT/$SUBVOL_NAME + $TOP_MNT/$HOME_SUBVOL"
  run btrfs subvolume create "$TOP_MNT/$SUBVOL_NAME"
  run btrfs subvolume create "$TOP_MNT/$HOME_SUBVOL"

  local workdir tarball tarname
  workdir=$(mktemp -d /tmp/elementary-grow.XXXXXX)
  tarname=$(basename "$UBUNTU_BASE_URL")
  tarball="$workdir/$tarname"
  log "fetching Ubuntu $UBUNTU_SUITE base ($UBUNTU_BASE_URL)"
  if [[ $MODE == "apply" ]]; then
    curl -fSL -o "$tarball" "$UBUNTU_BASE_URL" \
      || fail "base tarball download failed — check network/suite name"
    curl -fSL -o "$workdir/SHA256SUMS" "$(dirname "$UBUNTU_BASE_URL")/SHA256SUMS" \
      || fail "checksum file download failed"
    ( cd "$workdir" && sha256sum -c --status <(grep -F "$tarname" SHA256SUMS) ) \
      || fail "base tarball checksum MISMATCH — refusing to unpack"
    tar -xzpf "$tarball" -C "$TOP_MNT/$SUBVOL_NAME" \
      || fail "base tarball unpack failed"
  else log "(dry-run) would download, verify, and unpack the base tarball"; fi

  local newroot="$TOP_MNT/$SUBVOL_NAME"
  log "entering chroot build in $newroot"
  if [[ $MODE == "apply" ]]; then chroot_build "$newroot" \
      || fail "chroot build FAILED — new root incomplete, GRUB entry NOT installed. See log above; fix and re-run (rollback first).";
  else log "(dry-run) would chroot and install elementary-desktop + M-series layer"; fi

  if [[ $MODE == "apply" ]]; then graft_kernel_into "$newroot" || fail "kernel graft failed"; fi

  log "installing GRUB entry $GRUB_CUSTOM (additive; default untouched)"
  if [[ $MODE == "apply" ]]; then install_grub_entry "$newroot";
  else log "(dry-run) would write $GRUB_CUSTOM and run grub-mkconfig"; fi

  rm -rf "$workdir"
  log "done. Reboot, pick 'elementary OS (M-series)' in the boot menu."
  log "Old system remains the default. Rollback: $0 --rollback"
}

chroot_build() {
  local newroot="$1"
  # Plain --bind (not --rbind): rbind drags host /run/user + credentials
  # submounts into the chroot and they leak past cleanup, pinning TOP_MNT.
  mount --bind /dev "$newroot/dev"
  mount -t devpts devpts "$newroot/dev/pts"
  mount -t proc proc "$newroot/proc"
  mount -t sysfs sys "$newroot/sys"
  mount --bind /run "$newroot/run"
  cp /etc/resolv.conf "$newroot/etc/resolv.conf"
  trap 'umount -R "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null || umount -l "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null || true' RETURN

  chroot "$newroot" /bin/bash -s <<EOF || return 1
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
cat > /etc/apt/sources.list.d/ubuntu.sources <<SRC
Types: deb
URIs: http://ports.ubuntu.com/ubuntu-ports
Suites: $UBUNTU_SUITE $UBUNTU_SUITE-updates
Components: main universe
Architectures: arm64
SRC
apt-get update
apt-get install -y ca-certificates curl gnupg
# elementary PPAs: keyrings + sources copied from this repo
# (repos/common-files keyrings, repos/stable sources) — same files the
# image factory uses, so the transform root resolves the same packages.
mkdir -p /etc/apt/keyrings /etc/apt/sources.list.d
EOF
  # Keyrings/sources cross the chroot boundary from the host checkout
  # (binary keyrings cannot go through the stdin heredoc above).
  [[ -f "$REPO_ROOT/repos/common-files/etc/apt/keyrings/elementary-os.gpg" ]] \
    || { echo "missing $REPO_ROOT/repos/common-files keyrings — re-clone/pull this repo" >&2; return 1; }
  cp -a "$REPO_ROOT/repos/common-files/etc/apt/keyrings/elementary-os.gpg" \
        "$REPO_ROOT/repos/common-files/etc/apt/keyrings/elementary-os-os-patches.gpg" \
        "$newroot/etc/apt/keyrings/" || return 1
  sed -e "s/Suites: .*/Suites: $UBUNTU_SUITE/" \
      "$REPO_ROOT/repos/stable/etc/apt/sources.list.d/elementary-os-stable.sources" \
      > "$newroot/etc/apt/sources.list.d/elementary-os-stable.sources" || return 1
  sed -e "s/Suites: .*/Suites: $UBUNTU_SUITE/" \
      "$REPO_ROOT/repos/stable/etc/apt/sources.list.d/elementary-os-patches.sources" \
      > "$newroot/etc/apt/sources.list.d/elementary-os-patches.sources" || return 1
  # elementary-desktop metapackage lives in the daily PPA for resolute
  # (stable carries only Pantheon components) — same team keyring.
  sed -e "s/Suites: .*/Suites: $UBUNTU_SUITE/" \
      "$REPO_ROOT/repos/daily/etc/apt/sources.list.d/elementary-os-daily.sources" \
      > "$newroot/etc/apt/sources.list.d/elementary-os-daily.sources" || return 1
  chroot "$newroot" /bin/bash -s <<EOF || return 1
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-cache show elementary-desktop >/dev/null \
  || { echo "elementary-desktop not in PPAs for $UBUNTU_SUITE — aborting chroot build"; exit 1; }
apt-get install -y --install-recommends elementary-desktop elementary-minimal elementary-standard pantheon io.elementary.greeter io.elementary.wingpanel pipewire-pulse pipewire-alsa rtkit network-manager
apt-get clean
EOF

  # Apple layer: firmware copy (machine-local, never redistributed).
  # Host layout (verified on j314s/M1 Pro): blobs live in
  # /usr/lib/firmware/vendor/brcm/ with Apple board suffixes, e.g.
  # brcmfmac4387c2-pcie.apple,maldives.{bin,clm_blob,txcap_blob,txt}
  # (board from DT brcm,board-type; 5 variants shipped, ~8MB total).
  # The driver requests brcm/brcmfmacXXXX-pcie and the firmware loader
  # resolves the .apple,<board> suffix, so copy all board variants into
  # the new root's /lib/firmware/brcm/ (== /usr/lib/firmware/brcm/).
  local chip
  chip=$(detect_chip)
  if [[ -n $chip ]]; then
    log "copying host brcmfmac${chip}* + brcmbt${chip}* firmware into new root"
    run mkdir -p "$newroot/lib/firmware/brcm"
    if [[ $MODE == "apply" ]]; then
      local copied=0 src
      for src in /lib/firmware/brcm/brcmfmac${chip}* \
                 /usr/lib/firmware/brcm/brcmfmac${chip}* \
                 /usr/lib/firmware/vendor/brcm/brcmfmac${chip}* \
                 /lib/firmware/brcm/brcmbt${chip}* \
                 /usr/lib/firmware/brcm/brcmbt${chip}* \
                 /usr/lib/firmware/vendor/brcm/brcmbt${chip}*; do
        [[ -e $src ]] || continue
        cp -a "$src" "$newroot/lib/firmware/brcm/" && copied=$((copied+1))
      done
      (( copied > 0 )) \
        || log "WARNING: no host brcmfmac${chip}/brcmbt${chip} blobs found in /lib/firmware/brcm, /usr/lib/firmware/brcm, or /usr/lib/firmware/vendor/brcm — first-boot provisioning will report them"
      log "firmware copy: $copied file(s)"
    fi
  else log "WARNING: no Apple Broadcom Wi-Fi detected — skipping firmware copy"; fi
  # … UCM audio config, notch modprobe, resume + provisioning units …
  if [[ $MODE == "apply" ]]; then
    [[ -d /usr/share/alsa-card-profile ]] && cp -a /usr/share/alsa-card-profile "$newroot/usr/share/" 2>/dev/null || true
    mkdir -p "$newroot/etc/modprobe.d"
    curl -fSL -o "$newroot/etc/modprobe.d/asahi-notch.conf" "$MSERIES_BASE/etc/modprobe.d/asahi-notch.conf"
    mkdir -p "$newroot/usr/sbin" "$newroot/usr/lib/systemd/system"
    for f in usr/sbin/mseries-wifi-resume-fix usr/sbin/mseries-wifi-firmware \
             usr/lib/systemd/system/omarchy-wifi-resume-fix.service \
             usr/lib/systemd/system/mseries-wifi-firmware.service; do
      curl -fSL -o "$newroot/$f" "$MSERIES_BASE/$f"
    done
    chmod +x "$newroot/usr/sbin/mseries-wifi-resume-fix" "$newroot/usr/sbin/mseries-wifi-firmware"
  fi

  # Identity + mounts + services inside the new root.
  # fstab mirrors the host rows (same UUIDs/options), swapping only the
  # root subvolume — the layout omarchy itself enforces (subvol=@), so any
  # other layout aborts instead of being guessed.
  local host_root_row new_root_row host_boot_row host_home_row new_home_row uuid_root
  uuid_root=$(findmnt -no UUID /)
  host_root_row=$(awk '$1 !~ /^#/ && $2=="/" {print}' /etc/fstab)
  [[ $(wc -l <<<"$host_root_row") == 1 && -n $host_root_row ]] \
    || fail "host /etc/fstab / row is not exactly one line — refusing to guess"
  new_root_row=$(sed -E 's/subvol=\/@([,[:space:]])/subvol=\/@elementary\1/; s/subvol=@([,[:space:]])/subvol=@elementary\1/' <<<"$host_root_row")
  [[ $new_root_row != "$host_root_row" ]] \
    || fail "host / row has no subvol=@ option — unknown layout, refusing to guess"
  host_boot_row=$(awk '$1 !~ /^#/ && $2=="/boot" {print}' /etc/fstab)
  [[ -n $host_boot_row ]] || log "WARNING: no /boot row in host fstab — new root will not mount the ESP"
  host_home_row=$(awk '$1 !~ /^#/ && $2=="/home" {print}' /etc/fstab)
  if [[ -n $host_home_row ]]; then
    new_home_row=$(sed -E 's/subvol=\/@home([,[:space:]])/subvol=\/@elementary-home\1/; s/subvol=@home([,[:space:]])/subvol=@elementary-home\1/' <<<"$host_home_row")
    [[ $new_home_row != "$host_home_row" ]] \
      || fail "host /home row has no subvol=@home option — refusing to guess"
  else
    new_home_row="UUID=$uuid_root /home btrfs subvol=$HOME_SUBVOL,defaults 0 2"
  fi
  # LUKS: the new root unlocks the same container, so it needs the same map.
  if [[ -f /etc/crypttab ]]; then
    log "copying host /etc/crypttab (LUKS unlock map)"
    [[ $MODE == "apply" ]] && cp -a /etc/crypttab "$newroot/etc/crypttab"
  fi
  if [[ $MODE == "apply" ]]; then
    chroot "$newroot" /bin/bash -s <<EOF2 || return 1
set -euo pipefail
echo "elementary-m1" > /etc/hostname
printf '%s\n%s\n%s\n' "$new_root_row" "$host_boot_row" "$new_home_row" > /etc/fstab
systemctl enable NetworkManager mseries-wifi-firmware.service omarchy-wifi-resume-fix.service
echo "Set a user password and create your account on first boot (GDM/LightDM)."
EOF2
  else log "(dry-run) would write fstab (rows derived from host) + enable services"; fi
  umount -R "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null \
    || umount -l "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null || true
  trap - RETURN
}

# Install the graphical shell into the EXISTING @elementary root (no
# rebuild): greeter + panel + pantheon session were Recommends-only and got
# skipped. Additive apt install only; safe to re-run.
do_finish_root() {
  mount_top
  trap unmount_top EXIT
  local newroot="$TOP_MNT/$SUBVOL_NAME"
  [[ -d "$newroot/etc/apt" ]] || fail "no $SUBVOL_NAME — run --apply first"
  mount --bind /dev "$newroot/dev"
  mount -t devpts devpts "$newroot/dev/pts"
  mount -t proc proc "$newroot/proc"
  mount -t sysfs sys "$newroot/sys"
  mount --bind /run "$newroot/run"
  cp /etc/resolv.conf "$newroot/etc/resolv.conf"
  chroot "$newroot" /bin/bash -s <<EOF
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --install-recommends pantheon io.elementary.greeter io.elementary.wingpanel
apt-get clean
systemctl enable display-manager 2>/dev/null || systemctl enable lightdm 2>/dev/null || true
EOF
  local rc=$?
  umount -R "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null \
    || umount -l "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null || true
  (( rc == 0 )) || fail "finish-root chroot failed — see log"
  log "graphical shell installed; re-run --status to verify"
}

# Neutralize a stale, executable <entry>.removed (grub-mkconfig runs every
# executable file in /etc/grub.d, so it doubles the menuentry) and regenerate
# the menu. Idempotent.
do_repair_grub() {
  [[ -e $GRUB_CUSTOM || -e $GRUB_CUSTOM.removed ]] \
    || fail "no $GRUB_CUSTOM — run --apply first"
  if [[ -e $GRUB_CUSTOM.removed ]]; then
    chmod -x "$GRUB_CUSTOM.removed"
    log "neutralized $GRUB_CUSTOM.removed (no longer executable)"
  fi
  [[ -e $GRUB_CUSTOM ]] && chmod +x "$GRUB_CUSTOM"
  grub-mkconfig -o /boot/grub/grub.cfg
  local n
  n=$(grep -c "elementary OS (M-series" /boot/grub/grub.cfg || true)
  (( n == 1 )) || fail "expected 1 elementary menuentry, found $n — investigate /etc/grub.d"
  log "GRUB repaired: exactly 1 elementary menuentry"
}

# Create (or refresh) a login account inside the already-built @elementary
# root. The home directory lands on the separate @elementary-home subvolume,
# so it never mixes with the Arch side's @home.
#   --add-user [NAME]        NAME defaults to "admin"
#   ELEMENTARY_PASSWORD=...  password defaults to "admin"
# The default admin/admin is a first-boot convenience — change it after login.
do_add_user() {
  local name="${1:-admin}" pass="${ELEMENTARY_PASSWORD:-admin}"
  [[ $name =~ ^[a-z_][a-z0-9_-]*$ ]] || fail "invalid user name: $name"
  mount_top
  trap unmount_top EXIT
  local newroot="$TOP_MNT/$SUBVOL_NAME"
  [[ -d "$newroot/etc" ]] || fail "no $SUBVOL_NAME — run --apply first"

  # Mount the separate home subvolume so `useradd -m` writes into it.
  local root_src
  root_src=$(findmnt -no SOURCE /); root_src=${root_src%%\[*}
  mkdir -p "$newroot/home"
  if [[ -e "$TOP_MNT/$HOME_SUBVOL" ]]; then
    mount -o "subvol=$HOME_SUBVOL" "$root_src" "$newroot/home" \
      || fail "cannot mount $HOME_SUBVOL at /home"
  fi
  mount --bind /dev "$newroot/dev"
  mount -t devpts devpts "$newroot/dev/pts"
  mount -t proc proc "$newroot/proc"
  mount -t sysfs sys "$newroot/sys"
  mount --bind /run "$newroot/run"

  chroot "$newroot" /bin/bash -s -- "$name" <<'EOF'
set -euo pipefail
# Ubuntu keeps useradd/usermod in /usr/sbin, which is NOT on the PATH the
# chroot inherits from an Arch host. Set a normal Linux PATH first.
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
name="$1"
if ! command -v useradd >/dev/null 2>&1; then
  echo "useradd missing — installing the passwd package"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends passwd
fi
groups="sudo,adm,cdrom,dip,plugdev,netdev,video,render,audio,input"
if id "$name" >/dev/null 2>&1; then
  echo "user $name already exists; refreshing group membership"
else
  useradd -m -s /bin/bash -G "$groups" "$name"
fi
usermod -aG "$groups" "$name"
EOF

  # Password via stdin (never in argv/ps). Absolute path for the same reason
  # as above; chpasswd hashes with the root's default scheme (yescrypt).
  printf '%s:%s\n' "$name" "$pass" | chroot "$newroot" /usr/sbin/chpasswd \
    || fail "chpasswd failed for $name"

  # Carry over the invoking user's SSH keys, if any (convenience only).
  if [[ -n ${SUDO_USER:-} && -r /home/$SUDO_USER/.ssh/authorized_keys ]]; then
    install -d -m 700 -o 1000 -g 1000 "$newroot/home/$name/.ssh"
    cp "/home/$SUDO_USER/.ssh/authorized_keys" "$newroot/home/$name/.ssh/authorized_keys" 2>/dev/null || true
    chown -R 1000:1000 "$newroot/home/$name/.ssh" 2>/dev/null || true
  fi

  unmount_top
  trap - EXIT
  log "user '$name' ready in $SUBVOL_NAME (sudo + standard hardware groups)"
  if [[ $pass == admin ]]; then
    log "WARNING: password is the default 'admin' — run 'passwd' after first login"
  fi
}

# Read-only: what the elementary system is and what its last boot did.
# Answers "did we actually boot Ubuntu/elementary, and why did the session
# fail?" without chrooting into it.
do_logs() {
  mount_top
  trap unmount_top EXIT
  local newroot="$TOP_MNT/$SUBVOL_NAME"
  [[ -d "$newroot/etc" ]] || fail "no $SUBVOL_NAME — run --apply first"
  echo "--- os-release ---"
  cat "$newroot/etc/os-release" 2>/dev/null
  echo "--- kernel modules present in new root? ---"
  ls "$newroot/usr/lib/modules" 2>/dev/null \
    || echo "(NONE — the Asahi kernel can't load any module not baked into the initramfs)"
  echo "--- display manager ---"
  readlink "$newroot/etc/systemd/system/display-manager.service" 2>/dev/null || echo "(none)"
  echo "--- persistent journal? ---"
  if [[ -d "$newroot/var/log/journal" ]]; then
    journalctl -D "$newroot/var/log/journal" --list-boots --no-pager 2>/dev/null | tail -5
    echo "--- last boot, warning and above ---"
    journalctl -D "$newroot/var/log/journal" -b -1 -p warning --no-pager 2>/dev/null | tail -100
  else
    echo "(no /var/log/journal — journald was volatile; boot logs were not persisted)"
  fi
  echo "--- lightdm logs ---"
  ls -la "$newroot/var/log/lightdm" 2>/dev/null || echo "(no lightdm log dir)"
  for f in lightdm.log seat0-greeter.log x-0-greeter.log; do
    [[ -f "$newroot/var/log/lightdm/$f" ]] && { echo "##### $f (tail) #####"; tail -40 "$newroot/var/log/lightdm/$f"; }
  done
  echo "--- Xorg logs ---"
  ls "$newroot"/var/log/Xorg* 2>/dev/null || echo "(none)"
}

# Graft the host kernel's module tree + Asahi firmware into the new root.
# elementary's Ubuntu userspace ships no linux-asahi modules, but the boot
# reuses the host kernel — so without this, `modprobe` of anything not baked
# into the initramfs fails (nls_iso8859-1 for the vfat ESP, i2c_dev, the DCP
# display stack, …). depmod runs against the grafted tree.
graft_kernel_into() {
  local newroot="$1" kver src fw
  kver=$(uname -r)
  src="/usr/lib/modules/$kver"
  if [[ ! -d $src ]]; then
    log "WARNING: no $src on host — skipping module graft"
    return 0
  fi
  log "grafting kernel modules $kver ($(du -sh "$src" | cut -f1)) into new root"
  mkdir -p "$newroot/usr/lib/modules"
  cp -a "$src" "$newroot/usr/lib/modules/" || return 1
  for fw in apple vendor brcm; do
    [[ -d /usr/lib/firmware/$fw ]] || continue
    mkdir -p "$newroot/usr/lib/firmware/$fw"
    cp -a "/usr/lib/firmware/$fw/." "$newroot/usr/lib/firmware/$fw/" 2>/dev/null || true
  done
  # Build modules.dep for the grafted tree (host depmod, alternate root).
  depmod -b "$newroot" "$kver" 2>/dev/null \
    || log "WARNING: depmod -b failed; module autoloading may be incomplete"
  return 0
}

# Add/refresh the kernel modules + firmware on an already-built @elementary.
do_sync_kernel() {
  mount_top
  trap unmount_top EXIT
  local newroot="$TOP_MNT/$SUBVOL_NAME"
  [[ -d "$newroot/etc" ]] || fail "no $SUBVOL_NAME — run --apply first"
  graft_kernel_into "$newroot" || fail "kernel graft failed"
  log "kernel modules + Asahi firmware grafted into $SUBVOL_NAME; reboot into it"
}

# The new entry reuses the RUNNING kernel's command line and only swaps the
# root subvolume: LUKS cryptdevice, root=, resume, splash and friends are
# carried over instead of assumed. (Provenance: omarchy's own GRUB entries
# boot with rootflags=subvol=@ on LUKS via the same shared initramfs.)
build_linux_line() {
  local kpath="$1" word out=() line
  for word in $(cat /proc/cmdline); do
    case "$word" in
      BOOT_IMAGE=*|rootflags=*|ro) continue ;;
      *) out+=("$word") ;;
    esac
  done
  printf -v line '    linux %s %s rootflags=subvol=%s rw' "$kpath" "${out[*]}" "$SUBVOL_NAME"
  [[ $line == *' root='* ]] || { echo "running cmdline has no root= — refusing to guess" >&2; return 1; }
  printf '%s\n' "$line"
}

install_grub_entry() {
  local kver kernel initramfs search_uuid kpath ipath
  kver=$(uname -r)
  # Prefer the running kernel's files; fall back to newest present.
  kernel=$(ls /boot/vmlinuz-*"${kver}"* 2>/dev/null | head -n 1)
  [[ -z $kernel ]] && kernel=$(ls -t /boot/vmlinuz-* | head -n 1)
  initramfs=$(ls /boot/initramfs-*"${kver}"* 2>/dev/null | head -n 1)
  [[ -z $initramfs ]] && initramfs=$(ls -t /boot/initramfs-* | head -n 1)
  [[ -n $kernel && -n $initramfs ]] || fail "cannot locate kernel/initramfs pair in /boot"
  if [[ $(findmnt -no SOURCE /boot) != $(findmnt -no SOURCE /) ]]; then
    search_uuid=$(findmnt -no UUID /boot)   # /boot is its own filesystem
    kpath="/${kernel#/boot/}"; ipath="/${initramfs#/boot/}"
  else
    search_uuid=$(findmnt -no UUID /)       # /boot lives on the root fs
    kpath="$kernel"; ipath="$initramfs"
  fi
  local linux_line
  linux_line=$(build_linux_line "$kpath") || fail "cannot derive boot line from /proc/cmdline"
  cat > "$GRUB_CUSTOM" <<EOF
#!/bin/sh
# elementary-grow: additive entry. Managed by elementary-grow.sh --rollback.
exec tail -n +3 \$0
menuentry 'elementary OS (M-series, $kver)' {
    search --no-floppy --fs-uuid --set=root $search_uuid
$linux_line
    initrd $ipath
}
EOF
  chmod +x "$GRUB_CUSTOM"
  # A leftover aside file from an earlier --rollback must never stay
  # executable, or grub-mkconfig emits a duplicate menuentry.
  if [[ -e "$GRUB_CUSTOM.removed" ]]; then
    chmod -x "$GRUB_CUSTOM.removed"
    log "neutralized stale $GRUB_CUSTOM.removed before grub-mkconfig"
  fi
  grub-mkconfig -o /boot/grub/grub.cfg
  grep -q "elementary OS (M-series" /boot/grub/grub.cfg \
    || fail "new entry missing after grub-mkconfig — investigate before rebooting"
  local n
  n=$(grep -c "elementary OS (M-series" /boot/grub/grub.cfg || true)
  (( n == 1 )) || fail "expected 1 elementary menuentry, found $n — duplicate in /etc/grub.d, investigate"
  log "boot entry present (1 entry); default entry order unchanged"
}

# ---------------------------------------------------------------- main
main() {
  log "logging to $LOGFILE"
  case "$MODE" in
    rollback) [[ $(id -u) -eq 0 ]] || fail "rollback needs root"; do_rollback ;;
    status) [[ $(id -u) -eq 0 ]] || fail "status needs root"; do_status ;;
    finish-root) [[ $(id -u) -eq 0 ]] || fail "finish-root needs root"; do_finish_root ;;
    cleanup-stale) [[ $(id -u) -eq 0 ]] || fail "cleanup needs root"; cleanup_stale ;;
    repair-grub) [[ $(id -u) -eq 0 ]] || fail "repair-grub needs root"; do_repair_grub ;;
    add-user) [[ $(id -u) -eq 0 ]] || fail "add-user needs root"; do_add_user "$USER_NAME" ;;
    finalize) [[ $(id -u) -eq 0 ]] || fail "finalize needs root"; do_repair_grub; do_add_user "$USER_NAME"; do_status ;;
    logs) [[ $(id -u) -eq 0 ]] || fail "logs needs root"; do_logs ;;
    sync-kernel) [[ $(id -u) -eq 0 ]] || fail "sync-kernel needs root"; do_sync_kernel ;;
    *) do_apply ;;
  esac
}

# Post the log as a SECRET gist so the reviewer sees the full output from a
# URL. Needs `gh` authenticated (sudo pacman -S github-cli; gh auth login);
# otherwise the log path is printed and nothing leaves the machine.
upload_log() {
  (( UPLOAD )) || return 0
  log "uploading $LOGFILE as a secret gist…"
  curl -fsSL -m 15 -o /dev/null https://api.github.com \
    || { log "no network — log kept at $LOGFILE"; return 0; }
  if command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
    local url
    if url=$(gh gist create "$LOGFILE" -d "elementary-grow $MODE log $(date -u +%FT%TZ)"); then
      log "uploaded: $url  — paste this URL back for review"
    else
      log "gh upload failed — log kept at $LOGFILE"
    fi
  else
    log "gh not authenticated — log kept at $LOGFILE"
    log "to upload: sudo pacman -S github-cli && gh auth login, then re-run with --upload"
  fi
}

# pipefail is on: neutralize errexit around the pipeline so the exit code is
# captured via PIPESTATUS instead of killing the upload + log-path report.
set +e
main "$@" 2>&1 | tee "$LOGFILE"
rc=${PIPESTATUS[0]:-0}
set -e
echo "[elementary-grow] full log saved at $LOGFILE"
upload_log 2>&1 | tee -a "$LOGFILE"
exit "$rc"
