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
#   sudo ./elementary-grow.sh --isolate-boot # stop elementary's apt touching GRUB/initramfs/kernels
#
# Safety contract: additive-only. New subvolume, new GRUB menu entry, old
# system and default boot entry untouched. Every assumption in the design
# doc is a runtime check below; any failure aborts before changing
# anything. Must run as root ON the omarchy-mac system, never from macOS.
set -euo pipefail

MODE="dry-run"
UPLOAD=0
USER_NAME="${ELEMENTARY_USER:-}"
LOGFILE="${ELEMENTARY_GROW_LOG:-/tmp/elementary-grow-$(date +%Y%m%d-%H%M%S).log}"
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
    --isolate-boot) MODE="isolate-boot" ;;
    --dry-run) MODE="dry-run" ;;
    --upload) UPLOAD=1 ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    -*) echo "Unknown option: $arg (see --help)" >&2; exit 2 ;;
    *) USER_NAME="$arg" ;;
  esac
done

SUBVOL_NAME="@elementary"
# Goes into a root-run chroot script: only a valid hostname is acceptable.
if [[ -n ${ELEMENTARY_HOSTNAME:-} ]] && \
   ! [[ $ELEMENTARY_HOSTNAME =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]{0,251}[a-zA-Z0-9])?$ ]]; then
  echo "[elementary-grow] ABORT: invalid ELEMENTARY_HOSTNAME" >&2; exit 1
fi
HOME_SUBVOL="@elementary-home"
GRUB_CUSTOM="/etc/grub.d/40_elementary-grow"
SNAP_PREFIX="@.snapshots/elementary-grow"
MIN_FREE_GB=${ELEMENTARY_MIN_FREE_GB:-40}
CMDLINE_FILE=${ELEMENTARY_CMDLINE_FILE:-/proc/cmdline}   # overridable for tests
UBUNTU_SUITE="resolute"
UBUNTU_BASE_URL="https://cdimage.ubuntu.com/ubuntu-base/${UBUNTU_SUITE}/daily/current/${UBUNTU_SUITE}-base-arm64.tar.gz"
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
  compgen -G '/boot/vmlinuz-*' >/dev/null \
    || fail "no kernel image in /boot"
  compgen -G '/boot/initramfs-*' >/dev/null \
    || fail "no initramfs in /boot"
  log "preconditions OK (kernel $kver, ${free_gb}G free)"
}

detect_chip() {
  # Captured first: `lspci | grep -q` under pipefail fails intermittently when
  # grep exits on the first match and lspci takes SIGPIPE.
  local pci
  pci=$(lspci -nn 2>/dev/null || true)
  if grep -q "14e4:4425" <<<"$pci"; then echo "4378b1";
  elif grep -q "14e4:4433" <<<"$pci"; then echo "4387c2";
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
  find "$TOP_MNT/$SUBVOL_NAME/lib/firmware/brcm" -maxdepth 1 -name 'brcm*' 2>/dev/null | wc -l
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
    # The home subvolume holds the account's files: only delete it when it is
    # empty (a build that never got as far as creating the account), or when
    # the caller says so explicitly.
    if [[ -e "$TOP_MNT/$HOME_SUBVOL" ]] && \
       [[ -n $(ls -A "$TOP_MNT/$HOME_SUBVOL" 2>/dev/null) && ${ELEMENTARY_DELETE_HOME:-0} != 1 ]]; then
      log "KEEPING $HOME_SUBVOL: it contains files. Re-run with ELEMENTARY_DELETE_HOME=1 to delete it too."
    else
      run btrfs subvolume delete "$TOP_MNT/$HOME_SUBVOL" 2>/dev/null || true
    fi
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
    ( cd "$workdir" && sha256sum -c --status <(grep -E "[ *]${tarname}\$" SHA256SUMS) ) \
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

# Keep the elementary root's apt away from the shared boot chain (initramfs,
# GRUB, kernels). See mseries/install-boot-isolation.sh for the reasons.
isolate_boot_in() {
  local root="$1"
  install -m 755 "$REPO_ROOT/mseries/install-boot-isolation.sh" "$root/tmp/install-boot-isolation.sh" \
    || return 1
  chroot "$root" /bin/bash /tmp/install-boot-isolation.sh || return 1
  unlink "$root/tmp/install-boot-isolation.sh"
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
  # Before the desktop's packages (and their grub/initramfs maintainer scripts)
  # are installed, and again afterwards for the files those packages create.
  isolate_boot_in "$newroot" || return 1
  chroot "$newroot" /bin/bash -s <<EOF || return 1
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-cache show elementary-desktop >/dev/null \
  || { echo "elementary-desktop not in PPAs for $UBUNTU_SUITE — aborting chroot build"; exit 1; }
apt-get install -y --install-recommends elementary-desktop elementary-minimal elementary-standard pantheon io.elementary.greeter io.elementary.wingpanel pipewire-pulse pipewire-alsa rtkit network-manager
# Signal Desktop: official arm64 apt repo. The suite name really is
# 'xenial' (Signal never bumped it) — do not "correct" it. Non-fatal: a
# messaging app must not abort the whole root build. Flatpak
# (org.signal.Signal, Flathub) is the alternative transport — see
# mseries/packages.arm64.
rm -f /usr/share/keyrings/signal-desktop-keyring.gpg /tmp/signal-keys.asc
# The key is checked against Signal's published fingerprint before it is
# trusted; a key that does not match skips Signal rather than trusting it.
if curl -fsSL https://updates.signal.org/desktop/apt/keys.asc -o /tmp/signal-keys.asc \
   && [ "\$(gpg --show-keys --with-colons /tmp/signal-keys.asc | grep -m1 '^fpr' | cut -d: -f10)" = DBA36B5181D0C816F630E889D980A17457F6FB06 ] \
   && gpg --dearmor < /tmp/signal-keys.asc > /usr/share/keyrings/signal-desktop-keyring.gpg; then
  echo 'deb [arch=arm64 signed-by=/usr/share/keyrings/signal-desktop-keyring.gpg] https://updates.signal.org/desktop/apt xenial main' \
    > /etc/apt/sources.list.d/signal-desktop.list
  apt-get update
  apt-get install -y signal-desktop \
    || echo "WARNING: signal-desktop install failed (non-fatal)" >&2
else
  echo "WARNING: could not fetch a Signal key with the expected fingerprint — skipping Signal (non-fatal)" >&2
fi
rm -f /tmp/signal-keys.asc
# Speaker protection daemon (the safe default of mseries/install-audio-stack.sh).
# Non-fatal: the kernel keeps the speakers volume-locked without it.
apt-get install -y speakersafetyd \
  || echo "WARNING: speakersafetyd install failed (non-fatal)" >&2
apt-get clean
EOF
  isolate_boot_in "$newroot" || return 1
  # Swap on RAM for the zram setup below; non-fatal.
  chroot "$newroot" /bin/bash -c 'DEBIAN_FRONTEND=noninteractive apt-get install -y systemd-zram-generator' \
    || echo "WARNING: systemd-zram-generator install failed (non-fatal)" >&2
  # M-series enhancements (power policy, tuning, session helpers, theme, and the
  # first-boot job). ELEMENTARY_ENHANCE=0 skips them.
  if [[ ${ELEMENTARY_ENHANCE:-1} != 0 ]]; then
    bash "$REPO_ROOT/mseries/enhance.sh" --root "$newroot" || echo "WARNING: enhancements failed (non-fatal)" >&2
  fi

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
    local layer="$REPO_ROOT/mkosi.images/apple-silicon/mkosi.extra" f
    [[ -d /usr/share/alsa-card-profile ]] && cp -a /usr/share/alsa-card-profile "$newroot/usr/share/" 2>/dev/null || true
    # From the checkout this script runs from (so --ref is honoured and nothing
    # is fetched unauthenticated at build time).
    mkdir -p "$newroot/etc/modprobe.d" "$newroot/usr/sbin" "$newroot/usr/lib/systemd/system" \
             "$newroot/usr/libexec" "$newroot/etc/xdg/autostart"
    for f in etc/modprobe.d/asahi-notch.conf \
             usr/libexec/mseries-brightness etc/xdg/autostart/mseries-brightness.desktop \
             usr/sbin/mseries-wifi-resume-fix usr/sbin/mseries-wifi-firmware \
             usr/lib/systemd/system/omarchy-wifi-resume-fix.service \
             usr/lib/systemd/system/mseries-wifi-firmware.service; do
      [[ -f $layer/$f ]] || { echo "missing $layer/$f — re-clone/pull this repo" >&2; return 1; }
      cp -a "$layer/$f" "$newroot/$f" || return 1
    done
    chmod +x "$newroot/usr/sbin/mseries-wifi-resume-fix" "$newroot/usr/sbin/mseries-wifi-firmware" \
             "$newroot/usr/libexec/mseries-brightness"
    # Same timezone as the machine it grows on (the account is made with
    # useradd, which skips the first-run setup that would ask).
    if [[ -L /etc/localtime ]]; then
      ln -sf "$(readlink /etc/localtime)" "$newroot/etc/localtime"
      timedatectl show -p Timezone --value 2>/dev/null >"$newroot/etc/timezone" || true
    fi
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
echo "${ELEMENTARY_HOSTNAME:-elementary-m1}" > /etc/hostname
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
# Only groups that exist in this root: useradd aborts on an unknown one, and
# some (render, netdev) depend on which packages the build pulled in.
groups=""
for g in sudo adm cdrom dip plugdev netdev video render audio input; do
  if getent group "$g" >/dev/null; then groups="${groups:+$groups,}$g"; fi
done
if id "$name" >/dev/null 2>&1; then
  echo "user $name already exists; refreshing group membership"
else
  useradd -m -s /bin/bash "$name"
fi
[ -z "$groups" ] || usermod -aG "$groups" "$name"
EOF

  # Password via stdin (never in argv/ps). Absolute path for the same reason
  # as above; chpasswd hashes with the root's default scheme (yescrypt).
  # ELEMENTARY_PASSWORD_HASH (crypt(3) format) is what bin/elementary-mac-setup
  # passes so the plaintext never has to survive a reboot.
  if [[ -n ${ELEMENTARY_PASSWORD_HASH:-} ]]; then
    printf '%s:%s\n' "$name" "$ELEMENTARY_PASSWORD_HASH" | chroot "$newroot" /usr/sbin/chpasswd -e \
      || fail "chpasswd -e failed for $name"
    pass=""
  else
    printf '%s:%s\n' "$name" "$pass" | chroot "$newroot" /usr/sbin/chpasswd \
      || fail "chpasswd failed for $name"
  fi

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
  local newroot="$1" src kver fw grafted=0
  # Every module tree on the host, not just the running kernel's: the boot
  # entry names the kernel by file (vmlinuz-linux-asahi), which a host kernel
  # update replaces in place, so the entry may boot a newer kernel than the one
  # running now.
  for src in /usr/lib/modules/*/; do
    [[ -d $src ]] || continue
    kver=$(basename "$src")
    # Always re-copy: a rebuilt kernel keeps its version string (custom kernels do).
    log "grafting kernel modules $kver ($(du -sh "$src" | cut -f1)) into new root"
    mkdir -p "$newroot/usr/lib/modules"
    cp -a "${src%/}" "$newroot/usr/lib/modules/" || return 1
    # Build modules.dep for the grafted tree (host depmod, alternate root).
    depmod -b "$newroot" "$kver" 2>/dev/null \
      || log "WARNING: depmod -b failed for $kver; module autoloading may be incomplete"
    grafted=$((grafted+1))
  done
  (( grafted > 0 )) || log "WARNING: no module trees under /usr/lib/modules on host — skipping module graft"
  for fw in apple vendor brcm; do
    [[ -d /usr/lib/firmware/$fw ]] || continue
    mkdir -p "$newroot/usr/lib/firmware/$fw"
    cp -a "/usr/lib/firmware/$fw/." "$newroot/usr/lib/firmware/$fw/" 2>/dev/null || true
  done
  return 0
}

# Apply the boot isolation to an already-built @elementary (built before it
# existed). On the booted elementary system itself, run
# mseries/install-boot-isolation.sh directly instead.
do_isolate_boot() {
  mount_top
  trap unmount_top EXIT
  local newroot="$TOP_MNT/$SUBVOL_NAME"
  [[ -d "$newroot/etc" ]] || fail "no $SUBVOL_NAME — run --apply first"
  isolate_boot_in "$newroot" || fail "boot isolation failed"
  log "boot isolation applied to $SUBVOL_NAME"
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
root_is_crypt() {
  [[ $(lsblk -no TYPE "$(findmnt -no SOURCE / | sed 's/\[.*\]//')" 2>/dev/null) == crypt ]]
}

build_linux_line() {
  local kpath="$1" word out=() line
  for word in $(cat "$CMDLINE_FILE"); do
    case "$word" in
      BOOT_IMAGE=*|rootflags=*|ro|rw|appledrm.show_notch=*) continue ;;
      *) out+=("$word") ;;
    esac
  done
  # Pantheon centers Wingpanel content and has no notch avoidance. The
  # running omarchy cmdline may opt into the full-height mode, but the new
  # elementary entry must retain the rectangular safe display mode.
  out+=(appledrm.show_notch=0)
  # The elementary unlock screen (mseries/install-unlock-screen.sh) needs the
  # splash to be requested on the kernel line.
  if grep -qs '^Theme=elementary' /etc/plymouth/plymouthd.conf; then
    local have
    for have in quiet splash; do
      [[ " ${out[*]} " == *" $have "* ]] || out+=("$have")
    done
  fi
  printf -v line '    linux %s %s rootflags=subvol=%s rw' "$kpath" "${out[*]}" "$SUBVOL_NAME"
  [[ $line == *' root='* ]] || { echo "running cmdline has no root= — refusing to guess" >&2; return 1; }
  # On an encrypted root the initramfs can only open the container if the line
  # carries cryptdevice=. The boot that finishes an in-place encryption still
  # runs on the OLD command line (the new one only applies from the next boot),
  # so deriving from it would produce an entry that cannot unlock itself.
  if root_is_crypt && [[ $line != *' cryptdevice='* ]]; then
    echo "root is encrypted but the running cmdline has no cryptdevice= — reboot once, then re-run" >&2
    return 1
  fi
  printf '%s\n' "$line"
}

install_grub_entry() {
  local kver kernel initramfs search_uuid kpath ipath
  kver=$(uname -r)
  # The running kernel's files, as GRUB booted them: BOOT_IMAGE names the
  # kernel (vmlinuz-<flavour>) and its initramfs is initramfs-<flavour>.img.
  # Arch kernel files do not carry the version in their name, and several
  # flavours (stock, fairydust, fairydust-usb4) sit side by side in /boot, so
  # guessing by modification time picked a kernel the modules did not match.
  local bootimage flavour
  bootimage=$(tr ' ' '\n' <"$CMDLINE_FILE" | sed -n 's/^BOOT_IMAGE=//p' | head -n 1)
  flavour=$(basename "${bootimage:-none}"); flavour=${flavour#vmlinuz-}
  kernel=""; initramfs=""
  if [[ -f /boot/vmlinuz-$flavour && -f /boot/initramfs-$flavour.img ]]; then
    kernel=/boot/vmlinuz-$flavour
    initramfs=/boot/initramfs-$flavour.img
  else
    log "WARNING: cannot map BOOT_IMAGE='$bootimage' to a kernel/initramfs pair; guessing the newest"
    kernel=$(ls -t /boot/vmlinuz-* | head -n 1)
    initramfs=$(find /boot -maxdepth 1 -name 'initramfs-*.img' ! -name '*fallback*' -printf '%T@ %p\n' | sort -rn | head -n 1 | cut -d' ' -f2-)
  fi
  [[ -n $kernel && -n $initramfs ]] || fail "cannot locate kernel/initramfs pair in /boot"
  log "boot entry kernel: $kernel + $initramfs"
  if [[ $(findmnt -no SOURCE /boot) != $(findmnt -no SOURCE /) ]]; then
    search_uuid=$(findmnt -no UUID /boot)   # /boot is its own filesystem
    kpath="/${kernel#/boot/}"; ipath="/${initramfs#/boot/}"
  else
    search_uuid=$(findmnt -no UUID /)       # /boot lives on the root fs
    # Relative to the filesystem, subvolume included (/@/boot/vmlinuz-...):
    # GRUB reads the top level of the btrfs, not the @ subvolume.
    if command -v grub-mkrelpath >/dev/null; then
      kpath=$(grub-mkrelpath "$kernel"); ipath=$(grub-mkrelpath "$initramfs")
    else
      kpath="$kernel"; ipath="$initramfs"
    fi
  fi
  local linux_line
  linux_line=$(build_linux_line "$kpath") || fail "cannot derive boot line from /proc/cmdline"
  # `exec tail -n +3 $0` must be line 2: it copies everything from line 3 on
  # into grub.cfg. With a comment above it (as this once had) the exec line
  # itself was emitted into grub.cfg and GRUB reported an unknown command.
  cat > "$GRUB_CUSTOM" <<EOF
#!/bin/sh
exec tail -n +3 \$0
# elementary-grow: additive entry. Managed by elementary-grow.sh --rollback.
menuentry 'elementary OS (M-series, $kver)' --id elementary-mseries {
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
    isolate-boot) [[ $(id -u) -eq 0 ]] || fail "isolate-boot needs root"; do_isolate_boot ;;
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

# Sourcing the script (the tests do) defines the functions without running anything.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
# pipefail is on: neutralize errexit around the pipeline so the exit code is
# captured via PIPESTATUS instead of killing the upload + log-path report.
set +e
main "$@" 2>&1 | tee -a "$LOGFILE"
rc=${PIPESTATUS[0]:-0}
set -e
echo "[elementary-grow] full log saved at $LOGFILE"
upload_log 2>&1 | tee -a "$LOGFILE"
exit "$rc"
fi
