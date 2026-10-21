#!/usr/bin/env bash
# Hardware video decode on Apple Silicon (VA-API on the Apple Video Decoder).
#   bash mseries/install-video-decode.sh              # build, install, verify
#   bash mseries/install-video-decode.sh --uninstall  # remove the driver
#
# The kernel side is already there on Asahi kernels (CONFIG_VIDEO_APPLE_AVD=m: the apple_avd module
# probes at boot and creates a /dev/video* decoder) and so is the open replacement firmware
# (avd-fw, apple/avd-fw-*.bin, copied into the elementary root from the Asahi Alarm side). What
# Ubuntu lacks is the userspace bridge: the AVD is a *stateless* V4L2 decoder, which almost nothing
# speaks, so libva-v4l2_request translates VA-API into it. This builds omacom's fork (the one
# omarchy-mac ships as libva-v4l2_request-avd) from a pinned commit and installs it as both
# v4l2_request_drv_video.so and asahi_drv_video.so - the name libva derives from the DRM render node
# on Apple Silicon - so applications find it with no environment variable.
#
# Applications need their own VA-API support to use this bridge. Codec correctness and CPU/power
# benefits must be measured on the target hardware; compilation is not decode qualification.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

commit=c653eaa6234a02b5f31f77a8aa23f7a744650e87
sha256=0d8368fe7d1fea304acdc4903e2442486c880daffc37819fef687c8cecf34cf3
url=https://github.com/omacom/libva-v4l2_request/archive/$commit.tar.gz
render=/dev/dri/renderD128

driverdir=$(pkg-config --variable=driverdir libva 2>/dev/null || true)
driverdir=${AVD_DRIVERDIR:-${driverdir:-/usr/lib/aarch64-linux-gnu/dri}}   # AVD_DRIVERDIR: for tests

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f "$driverdir/v4l2_request_drv_video.so" "$driverdir/asahi_drv_video.so" /etc/sysctl.d/90-mseries-avd.conf
  echo 'Removed the VA-API driver.'
  exit 0
fi

[[ $(uname -m) == aarch64 ]] && grep -Faiq 'apple,' /proc/device-tree/compatible 2>/dev/null ||
  { echo 'Not an Apple Silicon machine.' >&2; exit 1; }
modinfo apple_avd >/dev/null 2>&1 ||
  { echo 'This kernel has no apple_avd module (CONFIG_VIDEO_APPLE_AVD); this module is not applicable here.' >&2; exit 1; }
compgen -G '/lib/firmware/apple/avd-fw-*' >/dev/null || compgen -G '/usr/lib/firmware/apple/avd-fw-*' >/dev/null ||
  echo 'Warning: no avd-fw-* firmware under /lib/firmware/apple; the decoder cannot start until it is installed.' >&2

for tool in meson ninja gcc pkg-config curl; do
  command -v "$tool" >/dev/null || { echo "Missing $tool (apt install meson ninja-build gcc pkg-config curl libva-dev libdrm-dev linux-libc-dev)." >&2; exit 1; }
done
pkg-config --exists libva || { echo 'Missing libva development files (apt install libva-dev libdrm-dev linux-libc-dev).' >&2; exit 1; }

work=$(mktemp -d "${TMPDIR:-/tmp}/avd-driver.XXXXXX")
trap 'rm -rf "$work"' EXIT
curl -fsSL --proto '=https' --tlsv1.2 --retry 3 -o "$work/src.tar.gz" "$url"
echo "$sha256  $work/src.tar.gz" | sha256sum --check --status || { echo 'Source archive checksum mismatch; refusing to build.' >&2; exit 1; }
tar -xzf "$work/src.tar.gz" -C "$work"
src=$(echo "$work"/libva-v4l2_request-*)

source "$here/lib-build.sh" 2>/dev/null && mseries_ccache_enable || true   # optional ccache (#47)
meson setup "$work/build" "$src" --prefix=/usr --buildtype=release -Dcodec_av1=enabled -Ddriverdir="$driverdir" >/dev/null
ninja -C "$work/build" src/v4l2_request_drv_video.so >/dev/null
built="$work/build/src/v4l2_request_drv_video.so"
test -s "$built"
if ldd "$built" | grep -q 'not found'; then
  echo 'The built driver has unresolved libraries; nothing installed.' >&2
  exit 1
fi

# Never overwrite someone else's asahi_drv_video.so (mesa may ship one one day).
if [[ -e $driverdir/asahi_drv_video.so && ! -L $driverdir/asahi_drv_video.so ]]; then
  echo "$driverdir/asahi_drv_video.so exists and is not ours; leaving it alone." >&2
  exit 1
fi
sudo install -D -m 0644 "$built" "$driverdir/v4l2_request_drv_video.so"
sudo ln -sf v4l2_request_drv_video.so "$driverdir/asahi_drv_video.so"

# The kernel driver allocates one large physically contiguous block per decode job (an order-10 kmalloc
# in avd_init_job; observed on an M1 Pro: "page allocation failure: order:10" followed by the VA-API
# driver reporting "decoder reported an error"). On a machine that has been up for a while that block
# can be unavailable, and 1080p decodes fail or hang until memory is compacted (tested: the same 1080p
# stream failed twice, then decoded bit-exact after `echo 1 > /proc/sys/vm/compact_memory`). Until the
# driver uses kvzalloc, ask the kernel to compact more eagerly in the background. This is a mitigation
# for fragmentation, not a fix, and it is not proven to remove every failure.
sudo install -D -m 0644 "$here/video-decode/90-mseries-avd.conf" /etc/sysctl.d/90-mseries-avd.conf
sudo sysctl -q -p /etc/sysctl.d/90-mseries-avd.conf 2>/dev/null || true

# Verify: the driver must bind to the decoder and offer at least H.264.
if command -v vainfo >/dev/null; then
  if out=$(vainfo --display drm --device "$render" 2>&1) && grep -q 'VAProfileH264' <<<"$out"; then
    echo "VA-API decode ready: $(grep -c 'VAEntrypointVLD' <<<"$out") decode profiles ($(grep -o 'VAProfile[A-Za-z0-9]*' <<<"$out" | sort -u | tr '\n' ' '))"
  else
    echo 'Installed, but vainfo could not bring the decoder up (the apple_avd module probes at boot: reboot once if the firmware was just added).' >&2
    printf '%s\n' "$out" | tail -8 >&2
    exit 1
  fi
else
  echo 'Installed. Run "vainfo" (apt install vainfo) to check the decoder.'
fi
