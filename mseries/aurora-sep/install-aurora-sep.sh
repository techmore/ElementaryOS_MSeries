#!/usr/bin/env bash
# Install the optional Aurora SEP kernel lane (Touch ID) on an M-series Mac.
#
#   install-aurora-sep.sh              dry run: print every change, change nothing
#   install-aurora-sep.sh --apply      install beside the running kernel
#   install-aurora-sep.sh --uninstall --apply  remove only the .20 lane
#   --with-touchid also installs/restores the unchanged SEP/libfprint userspace.
#   Without that flag, existing userspace and PAM remain untouched.
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
# Kernel/userspace come from omacom/linux-aurora release aurora-2026.10.17.20.
# Verify against SHA256SUMS from the same release; bump all three together.
AURORA_RELEASE=aurora-2026.10.17.20
AURORA_BASE=https://github.com/omacom/linux-aurora/releases/download/$AURORA_RELEASE
KVER=7.1.12-2-20261017.20-sep-ARCH
KERNEL_PKG=linux-aurora-7.1.12.aurora2-20261017.20-aarch64.pkg.tar.zst
KERNEL_SHA=49efa0ec088059aaae6c1fc7fef49521171abbab2c21a3d62bf670148dc0c7d8
TOUCHID_PKG=aurora-touchid-20261003-2-any.pkg.tar.zst
TOUCHID_SHA=84243a96fcabed344460c1dc67309730f03de34b9f1955faccbedc10c619c7c4
LIBFPRINT_VER=1.94.100-1.1
LIBFPRINT_PKG=libfprint-$LIBFPRINT_VER-aarch64.pkg.tar.zst
LIBFPRINT_SHA=bc7d9762db6644f2cfb58ddb209602c1d513845eb1498c098e01f12600fcbdf9
# Kernel source pin (for the record; the release asset carries the built tree):
#   omacom/linux-aurora, aurora-silicon/linux aurora-wip + SEP driver series
#   (aurora-silicon/linux#69, "Touch ID after reboot on M2 Max, M1 Pro and M1",
#    merged 2026-10-08), kernel commit c46d7dcdb8712ea9aeb0ce47b439ffae76371e55.

# ---- environment overrides (tests set these) ------------------------------
: "${ESP_UUID:=D893-79A4}"                 # EFI system partition filesystem UUID
: "${CMDLINE_FILE:=/etc/default/aurora-sep-cmdline}"
: "${GRUB_CUSTOM:=/boot/grub/custom.cfg}"   # never the generated grub.cfg
: "${SUFFIX:=aurora-sep-20261017.20}"       # -> /boot/vmlinuz-linux-asahi-$SUFFIX
: "${ENTRY_ID:=elementary-aurora20}"      # grub-reboot target
: "${ROOT_UUID:=}"                          # read from CMDLINE_FILE or /proc/cmdline
: "${CRYPTDEVICE:=}"
: "${MODULES_DIR:=/usr/lib/modules/$KVER}"
: "${LIBFPRINT_SO:=/usr/lib/aarch64-linux-gnu/libfprint-2.so.2.0.0}"
: "${DOWNLOAD_DIR:=/var/cache/elementary-aurora20}"

DRY_RUN=1
UNINSTALL=0
WITH_TOUCHID=0
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
: "${INITRAMFS_TOOL:=auto}"
: "${MKINITCPIO_CONFIG:=/etc/mkinitcpio.conf}"
: "${INITRAMFS_CONFIG:=/etc/initramfs-tools}"

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
    --with-touchid) WITH_TOUCHID=1 ;;
    --suffix) SUFFIX=$2; shift ;;
    --entry-id) ENTRY_ID=$2; shift ;;
    --cmdline) CMDLINE_FILE=$2; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; die "unknown option: $1" ;;
  esac
  shift
done

[[ $EUID -eq 0 || $DRY_RUN -eq 1 ]] || die "run with sudo for --apply/--uninstall"
[[ $SUFFIX =~ ^[a-zA-Z0-9._-]+$ && $ENTRY_ID =~ ^[a-zA-Z0-9._-]+$ ]] || die 'invalid suffix or entry id'
if (( ! DRY_RUN )); then
  [[ $(uname -s) == Linux && $(uname -m) == aarch64 ]] || die '--apply requires Linux aarch64'
  [[ -r /proc/device-tree/compatible ]] && grep -aq 'apple,' /proc/device-tree/compatible || die 'Apple Silicon required'
fi
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
    log "verified $name (cached)" >&2
  else
    step "download $name" >&2
    run "mkdir -p '$DOWNLOAD_DIR'" >&2
    run "curl -fsSL -o '$dest.part' '$AURORA_BASE/$name'" >&2
    [[ $DRY_RUN -eq 1 ]] || [[ "$(sha256sum "$dest.part" | cut -d' ' -f1)" == "$sha" ]] || die "checksum mismatch for $name"
    run "mv '$dest.part' '$dest'" >&2
    [[ $DRY_RUN -eq 1 ]] || [[ "$(sha256sum "$dest" | cut -d' ' -f1)" == "$sha" ]] || die "checksum mismatch for $name"
  fi
  printf '%s\n' "$dest"
}

grub_block() {
  cat <<EOF
# BEGIN elementary aurora20 (managed)
menuentry 'elementary OS (Aurora 20 kernel candidate)' --id $ENTRY_ID {
    search --no-floppy --fs-uuid --set=root $ESP_UUID
    linux /vmlinuz-linux-asahi-$SUFFIX root=UUID=$ROOT_UUID cryptdevice=$CRYPTDEVICE loglevel=3 quiet appledrm.show_notch=0 $ROOTFLAGS rw quiet splash
    initrd /initrd.img-$KVER
}
# END elementary aurora20
EOF
}

uninstall() {
  [[ $(uname -r) != "$KVER" ]] || die 'boot a recovery kernel before removing Aurora 20'
  step "remove the GRUB entry from $GRUB_CUSTOM"
  grub_args=(--file "$GRUB_CUSTOM" --remove)
  (( DRY_RUN )) || grub_args+=(--apply)
  python3 "$here/../aurora/grub-entry.py" "${grub_args[@]}"
  step "remove kernel image, initramfs and modules"
  run "$SUDO rm -f '$VMLINUZ' '$INITRD'"
  if command -v dpkg-query >/dev/null && dpkg-query -S "$MODULES_DIR/vmlinuz" >/dev/null 2>&1; then
    log 'Debian-managed modules retained; remove linux-image-elementary-aurora20 separately with apt'
  else
    run "$SUDO rm -rf '$MODULES_DIR'"
  fi
  (( WITH_TOUCHID )) || { log "existing Touch ID userspace retained"; return; }
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
if (( WITH_TOUCHID )); then
  touchid=$(download "$TOUCHID_PKG" "$TOUCHID_SHA")
  libfprint=$(download "$LIBFPRINT_PKG" "$LIBFPRINT_SHA")
fi

# The ESP carries the kernel and initramfs next to m1n1; make sure there is
# room before writing 60+ MB into it.
step "check ESP free space (need ~70 MB for image + initramfs)"
if [[ $DRY_RUN -eq 0 ]]; then
  actual_uuid=$(findmnt -rn --mountpoint /boot -o UUID)
  actual_type=$(findmnt -rn --mountpoint /boot -o FSTYPE)
  [[ $actual_uuid == "$ESP_UUID" && $actual_type == vfat ]] || die '/boot must be the vfat ESP matching ESP_UUID'
  free_mb=$(df -m /boot | awk 'NR==2{print $4}')
  (( free_mb > 128 )) || die "only ${free_mb} MiB free in /boot; at least 128 MiB required"
else
  echo "  [dry-run] df -m /boot"
fi

step "install kernel modules to $MODULES_DIR"
if (( ! DRY_RUN )); then
  stage=$(mktemp -d "$DOWNLOAD_DIR/kernel.XXXXXX")
  tar --zstd -xf "$kernel" -C "$stage" usr/lib/modules
  python3 - "$stage" "$here/../aurora" <<'PY'
import pathlib, sys
sys.path.insert(0, sys.argv[2])
from release import validate_kernel
validate_kernel(pathlib.Path(sys.argv[1]))
PY
  rm -rf "$stage"
fi
run "$SUDO mkdir -p $(dirname "$MODULES_DIR")"
run "$SUDO tar -C / -xpf '$kernel' usr/lib/modules usr/lib/modprobe.d"
run "$SUDO rm -f $MODULES_DIR/.BUILDINFO $MODULES_DIR/.MTREE $MODULES_DIR/.PKGINFO"
run "$SUDO depmod -a '$KVER'"

step "install kernel image and build the initramfs"
run "$SUDO install -D -m 0644 '$MODULES_DIR/vmlinuz' '$VMLINUZ'"
if [[ $INITRAMFS_TOOL == auto ]]; then
  if command -v mkinitcpio >/dev/null; then INITRAMFS_TOOL=mkinitcpio; else INITRAMFS_TOOL=initramfs-tools; fi
fi
if [[ $INITRAMFS_TOOL == mkinitcpio ]]; then
  if (( ! DRY_RUN )); then
    grep -Eq '^\s*HOOKS=' "$MKINITCPIO_CONFIG" || die 'known-good mkinitcpio config must include HOOKS'
    if [[ -n $CRYPTDEVICE ]]; then
      hooks=$(bash -c 'source "$1"; printf " %s " "${HOOKS[@]}"' _ "$MKINITCPIO_CONFIG")
      [[ $hooks == *' encrypt '* || $hooks == *' sd-encrypt '* ]] || die 'encrypted root requires encrypt/sd-encrypt in HOOKS'
    fi
    cp "$MKINITCPIO_CONFIG" "$DOWNLOAD_DIR/mkinitcpio.conf"
    printf '\nMODULES+=(appledrm drm_dma_helper dcp-fabric-core apple_sep thunderbolt phy_apple_atc)\n' >> "$DOWNLOAD_DIR/mkinitcpio.conf"
  fi
  run "$SUDO mkinitcpio -c '$DOWNLOAD_DIR/mkinitcpio.conf' -k '$KVER' -g '$INITRD'"
  if (( ! DRY_RUN )); then
    listing=$(lsinitcpio "$INITRD")
  fi
elif [[ $INITRAMFS_TOOL == initramfs-tools ]]; then
  if (( ! DRY_RUN )); then
    [[ -z $CRYPTDEVICE || -f /usr/share/initramfs-tools/hooks/cryptroot ]] || die 'encrypted root needs cryptsetup-initramfs'
    conf=$(mktemp -d "$DOWNLOAD_DIR/initramfs.XXXXXX")
    cp -a "$INITRAMFS_CONFIG/." "$conf/"
    printf '\nappledrm\ndrm_dma_helper\ndcp-fabric-core\napple_sep\nthunderbolt\nphy_apple_atc\n' >> "$conf/modules"
  else conf=$DOWNLOAD_DIR/initramfs-preview; fi
  run "$SUDO mkinitramfs -d '$conf' -o '$INITRD' '$KVER'"
  if (( ! DRY_RUN )); then
    listing=$(lsinitramfs "$INITRD")
    rm -rf "$conf"
  fi
else die "unknown INITRAMFS_TOOL: $INITRAMFS_TOOL"; fi
if (( ! DRY_RUN )); then
  for module in appledrm drm_dma_helper dcp-fabric-core apple-sep thunderbolt; do
    [[ $listing == *"$module.ko"* ]] || die "initramfs missing $module"
  done
fi
[[ $DRY_RUN -eq 1 ]] || [[ -f $INITRD ]] || die "initramfs missing: $INITRD"

step "write versioned candidate entry (non-default; legacy .19 retained)"
grub_args=(--file "$GRUB_CUSTOM")
(( DRY_RUN )) || grub_args+=(--apply)
grub_block | python3 "$here/../aurora/grub-entry.py" "${grub_args[@]}"

if (( WITH_TOUCHID )); then
step "install the Aurora libfprint (same SONAME as the distro build)"
if (( ! DRY_RUN )); then
  libstage=$(mktemp -d "$DOWNLOAD_DIR/libfprint.XXXXXX")
  tar --zstd -xf "$libfprint" -C "$libstage" --strip-components=3 usr/lib/libfprint-2.so.2.0.0
  ldd "$libstage/libfprint-2.so.2.0.0" > "$libstage/dependencies.txt"
  ! grep -q 'not found' "$libstage/dependencies.txt" || die 'missing libfprint dependencies; retain existing userspace'
else libstage=$DOWNLOAD_DIR/libfprint-preview; fi
if [[ -f $LIBFPRINT_SO ]]; then
  run "$SUDO cp -a '$LIBFPRINT_SO' '$LIBFPRINT_SO.pre-aurora-sep.$(date +%Y%m%d-%H%M%S)'"
fi
run "mkdir -p $(dirname "$LIBFPRINT_SO")"
run "$SUDO install -m 0644 '$libstage/libfprint-2.so.2.0.0' '$LIBFPRINT_SO'"
(( DRY_RUN )) || rm -rf "$libstage"

step "install the aurora-touchid userspace (units, setup tool)"
run "$SUDO tar -C / -xpf '$touchid' usr/bin usr/lib/aurora-touchid usr/lib/systemd/system/apple-sep.service usr/lib/systemd/system/apple-sep.path usr/lib/systemd/system/fprintd.service.d usr/lib/systemd/system-sleep"
run "$SUDO systemctl daemon-reload"
run "$SUDO systemctl enable apple-sep.path"

fi

step "done"
cat <<EOF

Candidate entry: $ENTRY_ID. No reboot or one-shot boot is armed.
Before a hardware test, stage/review the matched Aurora m1n1 + J314S DTB with
mseries/aurora/stage-boot.py. Shared boot.bin is NOT updated by this installer.
Follow mseries/aurora/README.md; retain the existing Fairydust/.19 recovery paths.

Then verify:
  uname -r                                   # $KVER
  systemctl status apple-sep.path apple-sep.service
  ls -la /dev/sep-bio                        # the enclave device
  fprintd-list \$USER                         # fprintd should see the SEP
  sudo aurora-touchid-setup                  # enrol a finger, verify, wire PAM

Rollback: restore any separately deployed boot.bin first, then use a recovery entry.
Remove this kernel lane: install-aurora-sep.sh --uninstall --apply
EOF
