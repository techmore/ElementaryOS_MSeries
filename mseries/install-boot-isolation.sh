#!/bin/bash
# Keep elementary's apt away from the boot chain. Run INSIDE an elementary root
# (as root): either directly on the booted elementary system, or by
# transform/elementary-grow.sh inside the chroot while it builds one.
#
# Why: elementary boots the kernel, initramfs and GRUB that the Asahi Alarm
# (Arch) side owns, all on the shared EFI partition mounted at /boot. The
# Ubuntu packages in the elementary root know nothing about that and would
# happily fight it:
#   - initramfs-tools: any package with an initramfs hook (plymouth theme,
#     cryptsetup, ...) runs update-initramfs, which writes initrd.img-* into
#     the small FAT /boot and is never used.
#   - grub2-common / grub-efi-arm64 are installed by the desktop; their
#     maintainer scripts run update-grub and grub-install, and update-grub
#     would overwrite the Arch-generated /boot/grub/grub.cfg (taking the Arch
#     and elementary menu entries with it).
#   - linux-image-generic/linux-generic would install an Ubuntu kernel nobody
#     boots, and run update-grub from its postinst.
# Idempotent. Undo: remove /etc/apt/preferences.d/00-mseries-no-kernel and
# `dpkg-divert --rename --remove` the three tools below.
set -euo pipefail

[[ $EUID -eq 0 ]] || { echo "run as root" >&2; exit 1; }

# 1. No initramfs generation (the Arch side builds the only initramfs).
if [[ -f /etc/initramfs-tools/update-initramfs.conf ]]; then
  sed -i 's/^update_initramfs=.*/update_initramfs=no/' /etc/initramfs-tools/update-initramfs.conf
fi

# 2. No Ubuntu kernels.
mkdir -p /etc/apt/preferences.d
cat >/etc/apt/preferences.d/00-mseries-no-kernel <<'EOF'
# The kernel is the Asahi kernel booted from the Arch side; see
# mseries/KERNEL-FLOW.md.
Package: linux-image-* linux-modules-* linux-generic* linux-signed-* linux-headers-*
Pin: release *
Pin-Priority: -1
EOF

# 3. Boot-loader tools become no-ops. A dpkg diversion keeps the stubs in place
#    when the grub packages are upgraded (the real files land at *.real).
for tool in update-grub grub-install grub-mkconfig; do
  path=/usr/sbin/$tool
  if ! dpkg-divert --list "$path" | grep -q .; then
    dpkg-divert --local --rename --divert "$path.real" --add "$path" >/dev/null
  fi
  cat >"$path" <<EOF
#!/bin/sh
echo "$tool: skipped - the boot loader and kernel are managed from the Asahi Alarm side (elementary-mac)" >&2
exit 0
EOF
  chmod 755 "$path"
done

echo "boot isolation in place"
