#!/bin/bash
# Compile-only check of every kernel patch in this kit, without the 40 GiB full build.
#
#   FAIRYDUST_CHECK_DIR=~/kernel-check bash mseries/fairydust/debian/compile-check.sh
#
# Fetches the pinned fairydust source (sha256-checked), applies the patches in the same order as
# build.sh (the USB4 series, then the packaging patches and the AVD fix), uses the repository's kernel
# config with the same symbol overrides as the real build, and compiles every directory the patches
# touch plus the Apple Silicon device trees that share the edited .dtsi files. Needs about 4 GiB, a
# native ARM64 toolchain, and no kernel headers: it does not produce an installable kernel, it
# answers "does this still compile".
#
# Rust support is switched off for this check (the patches touch only C and device trees), so
# rustc/bindgen are not needed.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
kit="$here/../usb4"
work=${FAIRYDUST_CHECK_DIR:-$HOME/.cache/mseries-kernel-check}
commit=ce9f2eba72c061a50b2d790450e90af3439d8c24
sha256=20ce358acffff4b3de86201975cd68c7aaf241ae010ec3cca9422bbe2b7f34aa

[[ $(uname -m) == aarch64 ]] || { echo 'Native ARM64 required' >&2; exit 2; }
[[ $EUID != 0 ]] || { echo 'Run as an ordinary user' >&2; exit 2; }
for tool in make gcc patch curl bison flex bc; do
  command -v "$tool" >/dev/null || { echo "Missing $tool (apt install build-essential bison flex bc libssl-dev libelf-dev)" >&2; exit 2; }
done
mkdir -p "$work"
free=$(df -PB1 "$work" | awk 'NR==2 {print $4}')
(( free >= 6 * 1024 * 1024 * 1024 )) || { echo 'Need about 6 GiB free' >&2; exit 2; }
cd "$work"

[[ -f src.tar.gz ]] || curl -fL --retry 4 --proto '=https' -o src.tar.gz "https://codeload.github.com/AsahiLinux/linux/tar.gz/$commit"
echo "$sha256  src.tar.gz" | sha256sum --check --status || { echo 'Source archive checksum mismatch' >&2; exit 1; }
echo "0d3540afc18751b236d816312b7a0d7311d2860476b1fce6668f6565ea04c3fd  $kit/config" | sha256sum --check --status ||
  { echo 'usb4/config changed: update the hash here and in build.sh after reviewing it' >&2; exit 1; }

# Always start from a clean tree so the patches are really what is being tested.
[[ ! -d source ]] || find source -delete
mkdir source
tar xzf src.tar.gz --strip-components=1 -C source
cd source
for patch in "$kit/0001-usb4-thunderbolt-apple-m1pro-on-fairydust.patch" \
             "$here/0001-runtime-dependencies.patch" \
             "$here/0002-precreate-apple-dtb-directory.patch" \
             "$here/0003-avd-job-segments-use-kvmalloc.patch"; do
  echo "applying $(basename "$patch")"
  patch --batch --fuzz=0 -p1 < "$patch" >/dev/null
done

out=$work/out
[[ ! -d $out ]] || find "$out" -delete
mkdir -p "$out"
cp "$kit/config" "$out/.config"
for symbol in TYPEC_DP_ALTMODE TYPEC_NVIDIA_ALTMODE TYPEC_TBT_ALTMODE USB4 USB4_APPLE_SOC RESET_APPLE_CIO \
              USB4_CONFIGFS USB4_STREAM USB4_NET VIDEO_APPLE_AVD; do
  scripts/config --file "$out/.config" --module "$symbol"
done
scripts/config --file "$out/.config" --enable CONFIGFS_FS --disable RUST --disable DEBUG_INFO_BTF
make O="$out" olddefconfig >/dev/null
make O="$out" -j"$(nproc)" modules_prepare >/dev/null

echo '== compiling every directory the patches touch'
make O="$out" -j"$(nproc)" drivers/thunderbolt/ drivers/net/thunderbolt/ drivers/reset/ drivers/phy/apple/ \
     drivers/usb/typec/ drivers/media/platform/apple/avd/ 2>&1 | grep -E 'error:|warning:|\*\*\*' && failed=1 || failed=0

for object in drivers/thunderbolt/apple.o drivers/thunderbolt/nhi.o drivers/thunderbolt/tb.o \
              drivers/thunderbolt/stream.o drivers/net/thunderbolt/main.o drivers/reset/reset-apple-cio.o \
              drivers/phy/apple/atc.o drivers/usb/typec/tipd/core.o drivers/usb/typec/class.o \
              drivers/media/platform/apple/avd/avd-drv.o; do
  if [[ -f $out/$object ]]; then echo "ok       $object"; else echo "MISSING  $object"; failed=1; fi
done
# The AVD fix must really be in the object: kvmalloc, not one big kmalloc.
nm "$out/drivers/media/platform/apple/avd/avd-drv.o" | grep -q __kvmalloc_node_noprof ||
  { echo 'FAIL: avd-drv.o does not use kvmalloc'; failed=1; }

echo '== device trees (shared .dtsi files feed every board below)'
for dts in t6000-j314s t6001-j316c t6020-j414s t6021-j416c t6022-j475d; do
  make O="$out" "apple/$dts.dtb" >/dev/null 2>&1 && echo "ok       $dts.dtb" || { echo "FAILED   $dts.dtb"; failed=1; }
done

echo "(source and objects kept in $work for inspection; delete the directory when done)"
(( failed == 0 )) && echo 'ALL KERNEL PATCHES COMPILE' || { echo 'COMPILE CHECK FAILED' >&2; exit 1; }
