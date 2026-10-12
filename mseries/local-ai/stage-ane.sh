#!/usr/bin/env bash
# Build an ANE candidate and private DTB. Never installs/loads a module or edits /boot.
set -euo pipefail
kernel=7.1.13-1-2-fairydust-usb4-ARCH
pin=000ef5f6b0ef3652dc3ce0233c23747c12c2f875
root=/mnt/fdbuild/root
build=/home/techmore/usb4-pkg/src/linux-fairydust/build/base
source_dir=${MSERIES_ANE_SOURCE:-$HOME/Documents/omarchy-ane}
stage=${MSERIES_ANE_STAGE:-$HOME/Documents/mseries-ane-staging}
[[ $(uname -r) == "$kernel" ]] || { echo 'Kernel changed; review the build and DTB paths first.' >&2; exit 1; }
[[ $(git -C "$source_dir" rev-parse HEAD) == "$pin" ]] || { echo 'Unexpected ANE source revision.' >&2; exit 1; }
[[ -z $(git -C "$source_dir" diff -- ane packaging/dt) ]] || { echo 'ANE driver or DT sources modified.' >&2; exit 1; }
for tool in dtc fdtoverlay fdtget; do command -v "$tool" >/dev/null || { echo 'Install device-tree-compiler.' >&2; exit 1; }; done
sudo mkdir -p "$root/tmp/mseries-ane-build"
sudo cp -a "$source_dir/ane/." "$root/tmp/mseries-ane-build/"
sudo chroot "$root" make -C /tmp/mseries-ane-build KERNELDIR="$build" ANE_VERSION="${pin:0:12}" -j2
mkdir -p "$stage"
sudo cp "$root/tmp/mseries-ane-build/ane.ko" "$stage/ane.ko"
sudo chown "$(id -u):$(id -g)" "$stage/ane.ko"
dtc -@ -I dts -O dtb -i "$source_dir/packaging/dt" -o "$stage/t6000-ane.dtbo" "$source_dir/packaging/dt/t6000-ane.dts"
base="$root/usr/lib/modules/$kernel/dtbs/t6000-j314s.dtb"
fdtoverlay -i "$base" -o "$stage/t6000-j314s-ane.dtb" "$stage/t6000-ane.dtbo"
[[ $(fdtget "$stage/t6000-j314s-ane.dtb" /soc/ane@284000000 compatible) == apple,t6000-ane ]]
[[ $(fdtget "$stage/t6000-j314s-ane.dtb" /soc/ane@284000000 status) == okay ]]
(cd "$stage" && sha256sum ane.ko t6000-ane.dtbo t6000-j314s-ane.dtb > SHA256SUMS)
echo "Staged only: $stage. Boot and installed kernel modules are unchanged."
