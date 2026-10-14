#!/bin/bash
# Install the CI-built usb4.4 kernel (linux-image-7.1.13-elementary-fairydust-usb4 .deb) beside the stock
# kernel on THIS Mac (elementary on subvol @elementary, Arch rescue on subvol @, ESP mounted at /boot).
#
#   sudo bash install-ci-kernel.sh /path/to/artifact-dir            # dry run: prints every step, changes nothing
#   sudo bash install-ci-kernel.sh /path/to/artifact-dir --apply    # does it
#
# Adds a TEST entry to /boot/grub/custom.cfg that is NOT the default; the stock entry stays the default.
# Unlike install-stage1/2.sh this takes the root, ESP and LUKS UUIDs from the running system.
#
# Boot image: the CI boot.bin embeds m1n1 1.5.2, which predates the USB4 tunables (see README "m1n1
# requirement"), so by default this script does NOT replace /boot/m1n1/boot.bin. It only saves a backup.
# Pass --with-ci-bootbin to install the CI image anyway (USB2 side of the dock only, expected).
set -euo pipefail

art=${1:?usage: $0 <artifact-dir> [--apply] [--with-ci-bootbin]}; shift || true
apply=0; with_bootbin=0
for a in "$@"; do case $a in --apply) apply=1 ;; --with-ci-bootbin) with_bootbin=1 ;; *) echo "unknown: $a" >&2; exit 2 ;; esac; done

run() { echo "+ $*"; (( apply )) && "$@" || true; }
die() { echo "ERROR: $*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || die "run as root (sudo)"
[[ $(uname -m) == aarch64 ]] || die "aarch64 only"
deb=$(compgen -G "$art/linux-image-*usb4*.deb" | head -1) || true
[[ -n $deb ]] || die "no linux-image-*usb4*.deb in $art"
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
[[ -e $esp/vmlinuz-linux-asahi-fairydust-usb4 ]] && die "already installed; remove it first"

stamp=$(date +%Y%m%d-%H%M%S); bak=/root/usb4-backup-$stamp
echo "== 1. backups (boot.bin lives on the ESP and runs before GRUB: keep a copy)"
run install -d "$bak"
run cp -a $esp/m1n1/boot.bin "$bak/boot.bin"
run cp -a $esp/m1n1/boot.bin $esp/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-$stamp
run cp -a $esp/grub/grub.cfg "$bak/grub.cfg"
[[ -f $esp/grub/custom.cfg ]] && run cp -a $esp/grub/custom.cfg "$bak/custom.cfg"

echo "== 2. unpack the kernel package"
stage=$(mktemp -d /var/tmp/usb4-stage.XXXXXX)
run dpkg-deb -x "$deb" "$stage"
run install -Dm644 "$stage/boot/vmlinuz-$kv" $esp/vmlinuz-linux-asahi-fairydust-usb4

echo "== 3. initramfs, built in the Arch root (subvol @) with mkinitcpio so cryptdevice= unlock works"
R=/mnt/usb4-arch
run mkdir -p $R
mountpoint -q $R || run mount -o subvol=@ "$root_dev" $R
for m in dev proc sys; do mountpoint -q $R/$m || run mount --bind /$m $R/$m; done
mountpoint -q $R/run || run mount -t tmpfs -o mode=755 tmpfs $R/run
mountpoint -q $R/boot || run mount --bind $esp $R/boot
run mkdir -p "$R/usr/lib/modules"
run cp -a "$stage/lib/modules/$kv" "$R/usr/lib/modules/$kv"
run chroot $R mkinitcpio -k "$kv" -g /boot/initramfs-linux-asahi-fairydust-usb4.img

echo "== 4. m1n1 boot image"
if (( with_bootbin )); then
  run install -m755 "$art/fairydust-m1n1-boot.bin" $esp/m1n1/boot.bin
else
  echo "(skipped: keeping the current boot.bin; see header comment)"
fi

echo "== 5. TEST grub entry (not the default)"
entry=$(cat <<EOG

menuentry 'elementary OS (M-series, fairydust + USB4 test)' --id elementary-usb4-test {
    search --no-floppy --fs-uuid --set=root $esp_uuid
    linux /vmlinuz-linux-asahi-fairydust-usb4 root=UUID=$root_uuid cryptdevice=UUID=$luks_uuid:root:allow-discards loglevel=3 quiet appledrm.show_notch=0 rootflags=subvol=@elementary rw quiet splash
    initrd /initramfs-linux-asahi-fairydust-usb4.img
}
EOG
)
if (( apply )); then
  grep -q elementary-usb4-test $esp/grub/custom.cfg 2>/dev/null || printf '%s\n' "$entry" >>$esp/grub/custom.cfg
else
  echo "+ append to $esp/grub/custom.cfg:$entry"
fi

echo "== 6. cleanup"
for m in boot run sys proc dev; do mountpoint -q $R/$m && run umount $R/$m; done
run umount $R
run rm -rf "$stage"

cat <<EOM

Done. $( ((apply)) || echo '(dry run: nothing was changed.)' )
Reboot and pick "fairydust + USB4 test" in GRUB. The default entry is unchanged.
Checks: uname -r; lsmod | grep thunderbolt; ls /sys/bus/thunderbolt/devices; lsusb -t
Rollback: pick the normal entry in GRUB. If the Mac stops before GRUB, restore boot.bin from macOS
(mseries/fairydust/usb4/RECOVERY.md); the copy is $bak/boot.bin and $esp/m1n1/boot.bin.KNOWN-GOOD-pre-usb4-$stamp.
EOM
