#!/bin/bash
# Install the CI-built usb4.4 kernel (linux-image-7.1.13-elementary-fairydust-usb4 .deb) beside the stock
# kernel on THIS Mac (elementary on subvol @elementary, Arch rescue on subvol @, ESP mounted at /boot).
#
#   sudo bash install-ci-kernel.sh /path/to/artifact-dir            # dry run: prints every step, changes nothing
#   sudo bash install-ci-kernel.sh /path/to/artifact-dir --apply    # does it
#
# --swap-dtb replaces only the j314s device tree inside the existing /boot/m1n1/boot.bin
# (keeping its newer m1n1) so a device-tree change such as the DP-tunnel experiment
# takes effect without replacing the whole boot image.
#
# Flags select a variant so kernels can be installed side by side:
#   sudo bash install-ci-kernel.sh <dir> --suffix fairydust-usb4-dptunnel \
#        --entry-id elementary-usb4-dptunnel --cmdline thunderbolt.allow_dp_tunnel=1
# (the KERNEL_SUFFIX / KERNEL_ENTRY_ID / KERNEL_EXTRA_CMDLINE env vars also work
# when the script is invoked directly, i.e. not through sudo.)
#
# Adds a TEST entry to /boot/grub/custom.cfg that is NOT the default; the stock entry stays the default.
# Unlike install-stage1/2.sh this takes the root, ESP and LUKS UUIDs from the running system.
#
# Boot image: the CI boot.bin embeds m1n1 1.5.2, which predates the USB4 tunables (see README "m1n1
# requirement"), so by default this script does NOT replace /boot/m1n1/boot.bin. It only saves a backup.
# Pass --with-ci-bootbin to install the CI image anyway (USB2 side of the dock only, expected).
set -euo pipefail

art=${1:?usage: $0 <artifact-dir> [--apply] [--with-ci-bootbin] [--swap-dtb]
                  [--suffix S] [--entry-id ID] [--cmdline C]}; shift || true
apply=0; with_bootbin=0; swap_dtb=0
# Variant selection. Defaults reproduce the original fairydust-usb4 install; the
# experimental USB4 DP-tunnel kernel uses
#   --suffix fairydust-usb4-dptunnel --entry-id elementary-usb4-dptunnel \
#   --cmdline thunderbolt.allow_dp_tunnel=1
# so both kernels can be installed side by side as separate GRUB entries.
# Flags are the reliable way to pass these: `VAR=... sudo cmd` is stripped by
# sudo's env_reset, so the KERNEL_* env vars only work for direct invocation.
sfx=${KERNEL_SUFFIX:-fairydust-usb4}
entry_id=${KERNEL_ENTRY_ID:-elementary-usb4-test}
extra=${KERNEL_EXTRA_CMDLINE:-}
while [[ $# -gt 0 ]]; do
  case $1 in
    --apply) apply=1 ;;
    --with-ci-bootbin) with_bootbin=1 ;;
    --swap-dtb) swap_dtb=1 ;;
    --suffix) sfx=${2:?--suffix needs a value}; shift ;;
    --entry-id) entry_id=${2:?--entry-id needs a value}; shift ;;
    --cmdline) extra=${2:?--cmdline needs a value}; shift ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

run() { echo "+ $*"; (( apply )) && "$@" || true; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo)"
[[ $(uname -m) == aarch64 ]] || die "aarch64 only"
deb=$(compgen -G "$art/linux-image-*usb4*.deb" | head -1) || true
if [[ -z $deb ]]; then
  # `gh run download -D dir` puts the files in dir/<artifact-name>/, so also
  # accept exactly one level of nesting.
  nested=$(compgen -G "$art/*/linux-image-*usb4*.deb" | head -1) || true
  if [[ -n $nested ]]; then
    art=$(dirname "$nested")
    deb=$nested
    echo "using nested artifact dir: $art"
  fi
fi
[[ -n $deb ]] || die "no linux-image-*usb4*.deb in $art (looked there and one level down)"
(cd "$art" && sha256sum -c SHA256SUMS --ignore-missing --quiet) || die "checksum mismatch in $art"

esp=/boot
mountpoint -q $esp || die "$esp (the ESP) is not mounted"
root_dev=$(findmnt -no SOURCE / | sed 's/\[.*//')
root_uuid=$(blkid -s UUID -o value "$root_dev")
luks_dev=$(cryptsetup status "$(basename "$root_dev")" | awk '/device:/{print $2}')
luks_uuid=$(blkid -s UUID -o value "$luks_dev")
esp_uuid=$(findmnt -no UUID $esp)
echo "root=$root_uuid luks=$luks_uuid esp=$esp_uuid"
[[ -n $root_uuid && -n $luks_uuid && -n $esp_uuid ]] || die "could not read UUIDs"

kv=$(dpkg-deb -c "$deb" | awk '{print $6}' | sed -n 's#^\./lib/modules/\([^/]*\)/$#\1#p' | head -1)
[[ -n $kv ]] || die "cannot read kernel release from $deb"
echo "kernel release: $kv"
[[ -e $esp/vmlinuz-linux-asahi-$sfx ]] && die "already installed; remove it first"

stamp=$(date +%Y%m%d-%H%M%S); bak=/root/usb4-backup-$stamp
echo "== 1. backups (boot.bin lives on the ESP and runs before GRUB: keep a copy)"
run install -d "$bak"
run cp -a $esp/m1n1/boot.bin "$bak/boot.bin"
run cp -a $esp/m1n1/boot.bin $esp/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-$stamp
run cp -a $esp/grub/grub.cfg "$bak/grub.cfg"
[[ -f $esp/grub/custom.cfg ]] && run cp -a $esp/grub/custom.cfg "$bak/custom.cfg"

echo "== 2. unpack the kernel package"
# A dry run must leave nothing behind, so don't create the staging directory.
if (( apply )); then
  stage=$(mktemp -d /var/tmp/usb4-stage.XXXXXX)
else
  stage=/var/tmp/usb4-stage.DRYRUN
fi
run dpkg-deb -x "$deb" "$stage"
run install -Dm644 "$stage/boot/vmlinuz-$kv" $esp/vmlinuz-linux-asahi-$sfx
# The modules must be in the system that BOOTS (this running root, subvol @elementary), not only in the
# Arch root used for mkinitcpio below. Without them /boot (FAT, needs nls_iso8859-1) cannot mount and
# boot drops to emergency mode (seen 2026-10-14).
# Copy the *contents*: `cp -a src dst` nests as dst/$(basename src) when dst
# already exists (i.e. on a second install of the same variant), which silently
# left the old modules in place on 2026-10-15 and made mkinitcpio bake the stale
# appledrm.ko (kms hook) into the initramfs.
run cp -a "$stage/lib/modules/$kv/." "/usr/lib/modules/$kv/"
run depmod -a "$kv"

echo "== 3. initramfs, built in the Arch root (subvol @) with mkinitcpio so cryptdevice= unlock works"
R=/mnt/usb4-arch
run mkdir -p $R
mountpoint -q $R || run mount -o subvol=@ "$root_dev" $R
for m in dev proc sys; do mountpoint -q $R/$m || run mount --bind /$m $R/$m; done
mountpoint -q $R/run || run mount -t tmpfs -o mode=755 tmpfs $R/run
mountpoint -q $R/boot || run mount --bind $esp $R/boot
run mkdir -p "$R/usr/lib/modules"
run cp -a "$stage/lib/modules/$kv/." "$R/usr/lib/modules/$kv/"
run chroot $R mkinitcpio -k "$kv" -g /boot/initramfs-linux-asahi-$sfx.img

echo "== 4. m1n1 boot image"
if (( with_bootbin )); then
  run install -m755 "$art/fairydust-m1n1-boot.bin" $esp/m1n1/boot.bin
elif (( swap_dtb )); then
  # Keep the current boot.bin (and its m1n1), replace only the j314s device tree
  # so the experimental crossbar routing takes effect. Byte-identical otherwise.
  dtb="$stage/usr/lib/linux-image-$kv/apple/t6000-j314s.dtb"
  here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
  run python3 "$here/swap-dtb.py" --in $esp/m1n1/boot.bin --dtb "$dtb" \
      --match apple,j314s --out $esp/m1n1/boot.bin.new
  run install -m755 $esp/m1n1/boot.bin.new $esp/m1n1/boot.bin
  run rm -f $esp/m1n1/boot.bin.new
else
  echo "(skipped: keeping the current boot.bin; see header comment)"
fi

echo "== 5. TEST grub entry (not the default)"
entry=$(cat <<EOG

menuentry 'elementary OS (M-series, $sfx test)' --id $entry_id {
    search --no-floppy --fs-uuid --set=root $esp_uuid
    linux /vmlinuz-linux-asahi-$sfx root=UUID=$root_uuid cryptdevice=UUID=$luks_uuid:root:allow-discards loglevel=3 quiet appledrm.show_notch=0 rootflags=subvol=@elementary rw quiet splash $extra
    initrd /initramfs-linux-asahi-$sfx.img
}
EOG
)
if (( apply )); then
  grep -q "$entry_id" $esp/grub/custom.cfg 2>/dev/null || printf '%s\n' "$entry" >>$esp/grub/custom.cfg
else
  echo "+ append to $esp/grub/custom.cfg:$entry"
fi

echo "== 6. cleanup"
for m in boot run sys proc dev; do mountpoint -q $R/$m && run umount $R/$m; done
run umount $R
run rm -rf "$stage"

cat <<EOM

Done. $( ((apply)) || echo '(dry run: nothing was changed.)' )
Reboot and pick the "$sfx test" entry in GRUB. The default entry is unchanged.
Checks: uname -r; lsmod | grep thunderbolt; ls /sys/bus/thunderbolt/devices; lsusb -t
Rollback: pick the normal entry in GRUB. If the Mac stops before GRUB, restore boot.bin from macOS
(mseries/fairydust/usb4/RECOVERY.md); the copy is $bak/boot.bin and $esp/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-$stamp.
EOM
