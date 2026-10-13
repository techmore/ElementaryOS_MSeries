#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
source "$SCRIPT_DIR/mseries/iso-label.sh"
cd "$SCRIPT_DIR/mkosi.output/"

SEARCH_DIR=.

DATE=$(just -f ../Justfile _get_timestamp)

PROFILE="${PROFILE:-unknown}"
ARCH=$(just -f ../Justfile _get_arch)

if [[ "$PROFILE" == "proposed" ]]; then
    SQUASHFS_LEVEL="${SQUASHFS_LEVEL:-3}"
else
    SQUASHFS_LEVEL="${SQUASHFS_LEVEL:-15}"
fi

ISO_LABEL=$(iso_volume_label "$PROFILE" "$ARCH")

case "$ARCH" in
    arm64|aarch64) DEB_ARCH=arm64 ;;
    x86-64|amd64) DEB_ARCH=amd64 ;;
    *) echo "error: Unsupported installer architecture: $ARCH" >&2; exit 1 ;;
esac

OUT_ISO="./elementaryos-9.0-${PROFILE}-${ARCH}.${DATE}.iso"

RAW_IMAGE=$(ls elementary_${DATE}.raw)

if [[ -z "$RAW_IMAGE" ]]; then
    echo "error: No .raw image found matching the pattern." >&2
    exit 1
fi

# Detect version
output_dir=$(ls -d liveiso_${DATE})

if [[ -z "$output_dir" ]]; then
    echo "error: No mkosi.output, run just do-daily or do-stable first." >&2
    exit 1
fi

base_name=$(basename "$output_dir")
echo "Detected release target: $base_name"

rm -rf iso_root

rsync -a --delete "${base_name}/iso_root/" iso_root/

echo "Writing minimal APT disc structure for apt-cdrom..."

mkdir -p "iso_root/dists/stable/main/binary-${DEB_ARCH}"
touch "iso_root/dists/stable/main/binary-${DEB_ARCH}/Packages"
gzip -kf "iso_root/dists/stable/main/binary-${DEB_ARCH}/Packages"
mkdir -p iso_root/pool

source ./base_${DATE}/usr/lib/os-release
sed -i "s|%PLACEHOLDER_VERSION%|$PRETTY_NAME|g" iso_root/boot/grub/grub.cfg
sed -i "s|%PLACEHOLDER_VERSION%|$PRETTY_NAME|g" iso_root/.disk/info
sed -i "s|%PLACEHOLDER_ARCH%|${ARCH})|g" iso_root/.disk/info


echo "Creating casper liveiso (zstd level ${SQUASHFS_LEVEL})..."

mkdir -p iso_root/extra

sudo podman run --rm -it \
--network host \
--dns 8.8.8.8 \
-v "$(pwd)":/workspace:Z \
-w /workspace \
ghcr.io/elementary/xorriso:tanit \
sh -c "set -e
           KERNEL_VERSION=\$(ls ${base_name}/lib/modules | head -n 1)
           chroot ${base_name} update-initramfs -u -k \${KERNEL_VERSION}
           cp ${base_name}/boot/vmlinuz-\${KERNEL_VERSION} iso_root/casper/vmlinuz
           cp ${base_name}/boot/initrd.img-\${KERNEL_VERSION} iso_root/casper/initrd
           rm -f iso_root/casper/filesystem.squashfs
           mksquashfs ${base_name} iso_root/casper/filesystem.squashfs -comp zstd -Xcompression-level ${SQUASHFS_LEVEL}
           echo 'Squashing raw image...'
           mksquashfs '$RAW_IMAGE' 'iso_root/extra/$(basename "$RAW_IMAGE").squashfs' -comp zstd -Xcompression-level ${SQUASHFS_LEVEL}
           grub-mkrescue -o ${OUT_ISO} -iso-level 3 -volid \"${ISO_LABEL}\" -appid \"elementary OS\" iso_root/
           echo 'Live environment generated!'"

rm -f custom_ubuntu_live.iso

echo "Success! Your live ISO is at: mkosi.output/$OUT_ISO"
