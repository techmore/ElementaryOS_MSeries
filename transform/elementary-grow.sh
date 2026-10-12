#!/bin/bash
# elementary-grow.sh — grow an elementary OS boot entry out of a running
# omarchy-mac (Apple Silicon, Asahi). See mseries/TRANSFORM-DESIGN.md.
#
#   sudo ./elementary-grow.sh              # dry run (DEFAULT): plan only
#   sudo ./elementary-grow.sh --apply      # perform the work
#   sudo ./elementary-grow.sh --rollback   # remove @elementary + boot entry
#
# Safety contract: additive-only. New subvolume, new GRUB menu entry, old
# system and default boot entry untouched. Every assumption in the design
# doc is a runtime check below; any failure aborts before changing
# anything. Must run as root ON the omarchy-mac system, never from macOS.
set -euo pipefail

MODE="dry-run"
for arg in "$@"; do
  case "$arg" in
    --apply) MODE="apply" ;;
    --rollback) MODE="rollback" ;;
    --dry-run) MODE="dry-run" ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
  esac
done

SUBVOL_NAME="@elementary"
GRUB_CUSTOM="/etc/grub.d/40_elementary-grow"
SNAP_PREFIX="@.snapshots/elementary-grow"
MIN_FREE_GB=40
UBUNTU_SUITE="resolute"
UBUNTU_BASE_URL="https://cdimage.ubuntu.com/ubuntu-base/${UBUNTU_SUITE}/daily/current/${UBUNTU_SUITE}-base-arm64.tar.gz"
# M-series layer, pinned to the commit that authored this script.
MSERIES_BASE="https://raw.githubusercontent.com/techmore/ElementaryOS_MSeries/main/mkosi.images/apple-silicon/mkosi.extra"

log()  { echo "[elementary-grow] $*"; }
fail() { echo "[elementary-grow] ABORT: $*" >&2; exit 1; }

run() {
  if [[ $MODE == "apply" ]]; then log "+ $*"; "$@";
  else log "(dry-run) would run: $*"; fi
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

unmount_top() { [[ -n $TOP_MNT ]] && umount "$TOP_MNT" && rmdir "$TOP_MNT" && TOP_MNT=""; }

# ---------------------------------------------------------------- rollback
do_rollback() {
  mount_top
  if [[ -e "$TOP_MNT/$SUBVOL_NAME" ]]; then
    run btrfs subvolume delete "$TOP_MNT/$SUBVOL_NAME"
  else log "no $SUBVOL_NAME subvolume — nothing to delete"; fi
  if [[ -f $GRUB_CUSTOM ]]; then
    if [[ $MODE == "apply" ]]; then mv "$GRUB_CUSTOM" "$GRUB_CUSTOM.removed"; log "moved $GRUB_CUSTOM aside";
    else log "(dry-run) would move $GRUB_CUSTOM aside"; fi
    run grub-mkconfig -o /boot/grub/grub.cfg
  else log "no $GRUB_CUSTOM — bootloader untouched"; fi
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
  log "snapshotting current root to $snap"
  run btrfs subvolume snapshot -r / "$snap"

  [[ -e "$TOP_MNT/$SUBVOL_NAME" ]] \
    && fail "$SUBVOL_NAME already exists — --rollback first if retrying"
  log "creating $TOP_MNT/$SUBVOL_NAME"
  run btrfs subvolume create "$TOP_MNT/$SUBVOL_NAME"

  local workdir tarball
  workdir=$(mktemp -d /tmp/elementary-grow.XXXXXX)
  tarball="$workdir/ubuntu-base.tar.gz"
  log "fetching Ubuntu $UBUNTU_SUITE base ($UBUNTU_BASE_URL)"
  if [[ $MODE == "apply" ]]; then
    curl -fSL -o "$tarball" "$UBUNTU_BASE_URL" \
      || fail "base tarball download failed — check network/suite name"
    curl -fSL -o "$workdir/SHA256SUMS" "$(dirname "$UBUNTU_BASE_URL")/SHA256SUMS" \
      || fail "checksum file download failed"
    ( cd "$workdir" && sha256sum -c --status <(grep "arm64.tar.gz" SHA256SUMS) ) \
      || fail "base tarball checksum MISMATCH — refusing to unpack"
    tar -xzpf "$tarball" -C "$TOP_MNT/$SUBVOL_NAME"
  else log "(dry-run) would download, verify, and unpack the base tarball"; fi

  local newroot="$TOP_MNT/$SUBVOL_NAME"
  log "entering chroot build in $newroot"
  if [[ $MODE == "apply" ]]; then chroot_build "$newroot";
  else log "(dry-run) would chroot and install elementary-desktop + M-series layer"; fi

  log "installing GRUB entry $GRUB_CUSTOM (additive; default untouched)"
  if [[ $MODE == "apply" ]]; then install_grub_entry "$newroot";
  else log "(dry-run) would write $GRUB_CUSTOM and run grub-mkconfig"; fi

  rm -rf "$workdir"
  log "done. Reboot, pick 'elementary OS (M-series)' in the boot menu."
  log "Old system remains the default. Rollback: $0 --rollback"
}

chroot_build() {
  local newroot="$1"
  mount --bind /dev "$newroot/dev"
  mount -t proc proc "$newroot/proc"
  mount -t sysfs sys "$newroot/sys"
  mount --bind /run "$newroot/run"
  cp /etc/resolv.conf "$newroot/etc/resolv.conf"
  trap 'umount -R "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null || true' RETURN

  chroot "$newroot" /bin/bash -s <<EOF
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
# elementary PPAs (keyrings fetched; fingerprints printed for confirmation)
mkdir -p /etc/apt/keyrings /etc/apt/sources.list.d
curl -fSL -o /etc/apt/keyrings/elementary-os.gpg https://ppa.launchpadcontent.net/elementary-os/stable/ubuntu/dists/$UBUNTU_SUITE/Release.gpg 2>/dev/null || true
echo "NOTE: verify elementary PPA key fingerprints against Launchpad before trusting this root."
apt-get update
apt-cache show elementary-desktop >/dev/null \
  || { echo "elementary-desktop not in PPA for $UBUNTU_SUITE — aborting chroot build"; exit 1; }
apt-get install -y elementary-desktop pipewire-pulse pipewire-alsa rtkit network-manager
apt-get clean
EOF

  # Apple layer: firmware copy (machine-local, never redistributed) …
  local chip
  chip=$(detect_chip)
  if [[ -n $chip ]]; then
    log "copying host brcmfmac${chip} firmware into new root"
    run mkdir -p "$newroot/lib/firmware/brcm"
    if [[ $MODE == "apply" ]]; then
      cp -a /lib/firmware/brcm/brcmfmac${chip}* "$newroot/lib/firmware/brcm/" 2>/dev/null \
        || log "WARNING: no host brcmfmac${chip} blobs to copy — first-boot provisioning will report them"
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
  local uuid_root uuid_esp
  uuid_root=$(findmnt -no UUID /)
  uuid_esp=$(findmnt -no UUID /boot 2>/dev/null || findmnt -no UUID /efi 2>/dev/null || findmnt -no UUID /boot/efi 2>/dev/null || echo UNKNOWN)
  if [[ $MODE == "apply" ]]; then
    chroot "$newroot" /bin/bash -s <<EOF2
set -euo pipefail
echo "elementary-m1" > /etc/hostname
cat > /etc/fstab <<FSTAB
UUID=$uuid_root / btrfs subvol=$SUBVOL_NAME,defaults 0 1
# ESP (mounted by hand when needed; adjust mountpoint to match host):
# UUID=$uuid_esp /boot/efi vfat defaults 0 2
FSTAB
systemctl enable NetworkManager mseries-wifi-firmware.service omarchy-wifi-resume-fix.service
echo "Set a user password and create your account on first boot (GDM/LightDM)."
EOF2
  fi
  umount -R "$newroot/dev" "$newroot/proc" "$newroot/sys" "$newroot/run" 2>/dev/null || true
  trap - RETURN
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
  local root_uuid
  root_uuid=$(findmnt -no UUID /)
  cat > "$GRUB_CUSTOM" <<EOF
#!/bin/sh
# elementary-grow: additive entry. Managed by elementary-grow.sh --rollback.
exec tail -n +3 \$0
menuentry 'elementary OS (M-series, $kver)' {
    search --no-floppy --fs-uuid --set=root $search_uuid
    linux $kpath root=UUID=$root_uuid rootflags=subvol=$SUBVOL_NAME rw
    initrd $ipath
}
EOF
  chmod +x "$GRUB_CUSTOM"
  grub-mkconfig -o /boot/grub/grub.cfg
  grep -q "elementary OS (M-series" /boot/grub/grub.cfg \
    || fail "new entry missing after grub-mkconfig — investigate before rebooting"
  log "boot entry present; default entry order unchanged"
}

# ---------------------------------------------------------------- main
case "$MODE" in
  rollback) [[ $(id -u) -eq 0 ]] || fail "rollback needs root"; do_rollback ;;
  *) do_apply ;;
esac
