#!/usr/bin/env bash
# Install the optional Aurora SEP kernel lane (Touch ID) on an M-series Mac.
#
#   install-aurora-sep.sh              dry run: print every change, change nothing
#   install-aurora-sep.sh --apply      install beside the running kernel
#   install-aurora-sep.sh --uninstall  remove the lane again
#
# The lane installs the community Aurora kernel (omacom/linux-aurora) plus the
# Apple SEP driver and its userspace beside the existing kernels. It never
# becomes the default boot entry: GRUB gains one extra menuentry in
# /boot/grub/custom.cfg, marked for clean removal.
#
# What Touch ID can and cannot do here (keep this honest in every doc):
#   can:   unlock sudo, polkit prompts and the login greeter (PAM/fprintd)
#   can't: unlock the LUKS root at boot (the SEP is asleep that early and
#          Apple Silicon has no TPM) -- the disk passphrase is unchanged
#
# Upstream is community, not Asahi: Asahi lists Touch ID as unsupported. The
# Aurora driver talks to the Secure Enclave directly. Results below are what
# this machine has demonstrably done, not what upstream claims.
set -euo pipefail

# ---- pins (public source revisions + checksums) --------------------------
# Kernel/userspace come from omacom/linux-aurora release aurora-2026.10.15.19.
# Verify against SHA256SUMS from the same release; bump all three together.
AURORA_RELEASE=aurora-2026.10.15.19
AURORA_BASE=https://github.com/omacom/linux/releases/download/$AURORA_RELEASE
KVER=7.1.12-2-20261015.19-sep-ARCH
KERNEL_PKG=linux-aurora-7.1.12.aurora2-20261015.19-aarch64.pkg.tar.zst
KERNEL_SHA=38546cb550075a01f9465bcf7d90ef6690c42d820da7df80f130aa49bd9b69c9
TOUCHID_PKG=aurora-touchid-20261003-2-any.pkg.tar.zst
TOUCHID_SHA=84243a96fcabed344460c1dc67309730f03de34b9f1955faccbedc10c619c7c4
LIBFPRINT_VER=1.94.100-1.1
LIBFPRINT_PKG=libfprint-$LIBFPRINT_VER-aarch64.pkg.tar.zst
LIBFPRINT_SHA=bc7d9762db6644f2cfb58ddb209602c1d513845eb1498c098e01f12600fcbdf9
# Kernel source pin (for the record; the release asset carries the built tree):
#   omacom/linux-aurora, aurora-silicon/linux aurora-wip + SEP driver series
#   (aurora-silicon/linux#69, "Touch ID after reboot on M2 Max, M1 Pro and M1",
#    merged 2026-10-08), kernel commit 5ec1028c81526e1ed31db2b97e47edf8663e83cb.

# ---- environment overrides (tests set these) ------------------------------
: "${ESP_UUID:=D893-79A4}"                 # EFI system partition filesystem UUID
: "${CMDLINE_FILE:=/etc/default/aurora-sep-cmdline}"
: "${GRUB_CUSTOM:=/boot/grub/custom.cfg}"   # never the generated grub.cfg
: "${SUFFIX:=aurora-sep-20261015.19}"       # -> /boot/vmlinuz-linux-asahi-$SUFFIX
: "${ENTRY_ID:=elementary-aurora-sep}"      # grub-reboot target
: "${ROOT_UUID:=}"                          # read from CMDLINE_FILE or /proc/cmdline
: "${CRYPTDEVICE:=}"
: "${MODULES_DIR:=/usr/lib/modules/$KVER}"
: "${LIBFPRINT_SO:=/usr/lib/aarch64-linux-gnu/libfprint-2.so.2.0.0}"
: "${DOWNLOAD_DIR:=${TMPDIR:-/tmp}/aurora-sep}"

DRY_RUN=1
UNINSTALL=0

log()  { printf '\033[1;32m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mwarning:\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31merror:\033[0m %s\n' "$*" >&2; exit 1; }

run() {
  if (( DRY_RUN )); then printf '  [dry-run] %s\n' "$*"; else eval "$*"; fi
}

usage() { sed -n '2,12s/^# \{0,1\}//p' "$0"; }

# Run `cmd` unless dry run, and honour --apply. Same shape as the fairydust
# install-ci-kernel.sh runner so reviewers read the two the same way.
step() { printf '\033[1;36m-- %s\033[0m\n' "$*"; }

while (( $# )); do
  case $1 in
    --apply) DRY_RUN=0 ;;
    --uninstall) UNINSTALL=1 ;;
    --suffix) SUFFIX=$2; shift ;;
    --entry-id) ENTRY_ID=$2; shift ;;
    --cmdline) CMDLINE_FILE=$2; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

[[ $EUID -eq 0 || $DRY_RUN -eq 1 ]] || die "run with sudo for --apply/--uninstall"
SUDO=""; (( EUID == 0 )) || SUDO=sudo

VMLINUZ=/boot/vmlinuz-linux-asahi-$SUFFIX
INITRD=/boot/initrd.img-$KVER

# The live machine boots through GRUB; the generated grub.cfg is owned by the
# distro tooling, so the lane only ever appends a marked block to custom.cfg.
read_cmdline() {
  if [[ -f $CMDLINE_FILE ]]; then
    # shellcheck disable=SC1090
    source "$CMDLINE_FILE"   # sets ROOT_UUID / CRYPTDEVICE
  fi
  if [[ -z $ROOT_UUID ]]; then
    ROOT_UUID=$(awk '{for(i=1;i<=NF;i++) if($i ~ /^root=UUID=/) {sub(/^root=UUID=/,"",$i); print $i}}' /proc/cmdline)
    CRYPTDEVICE=$(awk '{for(i=1;i<=NF;i++) if($i ~ /^cryptdevice=/) {sub(/^cryptdevice=/,"",$i); print $i}}' /proc/cmdline)
  fi
}

download() { # name sha
  local name=$1 sha=$2 dest=$DOWNLOAD_DIR/$1
  if [[ -f $dest ]] && [[ "$(sha256sum "$dest" | cut -d' ' -f1)" == "$sha" ]]; then
    log "verified $name (cached)"
  else
    step "download $name"
    run "mkdir -p '$DOWNLOAD_DIR'"
    run "curl -fsSL -o '$dest.part' '$AURORA_BASE/$name'"
    run "mv '$dest.part' '$dest'"
    [[ $DRY_RUN -eq 1 ]] || [[ "$(sha256sum "$dest" | cut -d' ' -f1)" == "$sha" ]] || die "checksum mismatch for $name"
  fi
  printf '%s\n' "$dest"
}

grub_block() {
  cat <<EOF
# BEGIN elementary aurora-sep (managed: install-aurora-sep.sh)
menuentry 'elementary OS (Aurora SEP kernel - Touch ID)' --id $ENTRY_ID {
    search --no-floppy --fs-uuid --set=root $ESP_UUID
    linux /vmlinuz-linux-asahi-$SUFFIX root=UUID=$ROOT_UUID cryptdevice=$CRYPTDEVICE loglevel=3 quiet appledrm.show_notch=0 $ROOTFLAGS rw quiet splash
    initrd /initrd.img-$KVER
}
# END elementary aurora-sep
EOF
}

uninstall() {
  step "remove the GRUB entry from $GRUB_CUSTOM"
  if [[ -f $GRUB_CUSTOM ]] && grep -q 'BEGIN elementary aurora-sep' "$GRUB_CUSTOM"; then
    run "$SUDO cp -a '$GRUB_CUSTOM' '$GRUB_CUSTOM.pre-aurora-sep.$(date +%Y%m%d-%H%M%S)'"
    run "$SUDO sed -i '/BEGIN elementary aurora-sep/,/END elementary aurora-sep/d' '$GRUB_CUSTOM'"
  else
    log "no aurora-sep entry in $GRUB_CUSTOM"
  fi
  step "remove kernel image, initramfs and modules"
  run "$SUDO rm -f '$VMLINUZ' '$INITRD'"
  run "$SUDO rm -rf '$MODULES_DIR'"
  step "restore the distro libfprint from the newest .pre-aurora-sep backup"
  local backup
  backup=$(ls -1t "$LIBFPRINT_SO".pre-aurora-sep.* 2>/dev/null | head -1 || true)
  if [[ -n $backup ]]; then
    run "$SUDO cp -a '$backup' '$LIBFPRINT_SO'"
  else
    warn "no libfprint backup found; reinstall libfprint-2 from apt"
  fi
  step "remove the aurora-touchid userspace and disable apple-sep.path"
  run "$SUDO rm -rf /usr/lib/aurora-touchid /usr/bin/aurora-touchid-setup"
  run "$SUDO rm -f /usr/lib/systemd/system/apple-sep.service /usr/lib/systemd/system/apple-sep.path /usr/lib/systemd/system/fprintd.service.d/aurora.conf /usr/lib/systemd/system-sleep/aurora-touchid"
  run "$SUDO systemctl disable apple-sep.path"
  run "$SUDO systemctl daemon-reload"
  log "removed. Enrolled fingerprints stay in fprintd; clear with: fprintd-delete \$USER"
}

if (( UNINSTALL )); then uninstall; exit 0; fi

read_cmdline
[[ -n $ROOT_UUID ]] || die "could not determine ROOT_UUID (set it in $CMDLINE_FILE)"
: "${ROOTFLAGS:=rootflags=subvol=@elementary}"

kernel=$(download "$KERNEL_PKG" "$KERNEL_SHA")
touchid=$(download "$TOUCHID_PKG" "$TOUCHID_SHA")
libfprint=$(download "$LIBFPRINT_PKG" "$LIBFPRINT_SHA")

# The ESP carries the kernel and initramfs next to m1n1; make sure there is
# room before writing 60+ MB into it.
step "check ESP free space (need ~70 MB for image + initramfs)"
if [[ $DRY_RUN -eq 0 ]]; then
  free_mb=$(df -m /boot | awk 'NR==2{print $4}')
  (( free_mb > 90 )) || warn "only ${free_mb} MB free in /boot; prune old initramfs-linux-asahi-*.img test images first"
else
  echo "  [dry-run] df -m /boot"
fi

step "install kernel modules to $MODULES_DIR"
run "$SUDO mkdir -p $(dirname "$MODULES_DIR")"
run "$SUDO tar -C / -xpf '$kernel' usr/lib/modules usr/lib/modprobe.d"
run "$SUDO rm -f $MODULES_DIR/.BUILDINFO $MODULES_DIR/.MTREE $MODULES_DIR/.PKGINFO"
run "$SUDO depmod -a '$KVER'"

step "install kernel image and build the initramfs"
run "$SUDO install -D -m 0644 '$MODULES_DIR/vmlinuz' '$VMLINUZ'"
run "$SUDO update-initramfs -c -k '$KVER'"
[[ $DRY_RUN -eq 1 ]] || [[ -f $INITRD ]] || die "initramfs missing: $INITRD"

step "append the GRUB entry (non-default; grub-reboot $ENTRY_ID to try it)"
if [[ -f $GRUB_CUSTOM ]] && grep -q "BEGIN elementary aurora-sep" "$GRUB_CUSTOM"; then
  warn "aurora-sep entry already present in $GRUB_CUSTOM; leaving it"
else
  run "$SUDO cp -a '$GRUB_CUSTOM' '$GRUB_CUSTOM.pre-aurora-sep.$(date +%Y%m%d-%H%M%S)'"
  run "$SUDO tee -a '$GRUB_CUSTOM' >/dev/null <<BLOCK
$(grub_block)

BLOCK"
fi

step "install the Aurora libfprint (same SONAME as the distro build)"
if [[ -f $LIBFPRINT_SO ]]; then
  run "$SUDO cp -a '$LIBFPRINT_SO' '$LIBFPRINT_SO.pre-aurora-sep.$(date +%Y%m%d-%H%M%S)'"
fi
run "mkdir -p $(dirname "$LIBFPRINT_SO")"
run "mkdir -p /tmp/aurora-sep-libfprint"
run "tar --zstd -xf '$libfprint' -C /tmp/aurora-sep-libfprint --strip-components=3 usr/lib/libfprint-2.so.2.0.0"
run "$SUDO install -m 0644 /tmp/aurora-sep-libfprint/libfprint-2.so.2.0.0 '$LIBFPRINT_SO'"

step "install the aurora-touchid userspace (units, setup tool)"
run "$SUDO tar -C / -xpf '$touchid' usr/lib usr/bin"
run "$SUDO systemctl daemon-reload"
run "$SUDO systemctl enable apple-sep.path"

step "done"
cat <<EOF

Reboot with:   sudo grub-reboot $ENTRY_ID && systemctl reboot
(Dock: the community j314s reports had flaky boots with a Thunderbolt display
attached -- detach the dock for the first boot.)

Then verify:
  uname -r                                   # $KVER
  systemctl status apple-sep.path apple-sep.service
  ls -la /dev/sep-bio                        # the enclave device
  fprintd-list \$USER                         # fprintd should see the SEP
  sudo aurora-touchid-setup                  # enrol a finger, verify, wire PAM

Rollback: pick any other GRUB entry, or: install-aurora-sep.sh --uninstall
EOF
