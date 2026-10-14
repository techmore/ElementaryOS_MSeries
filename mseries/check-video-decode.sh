#!/bin/bash
# Hardware decode check on the real machine: H.264 at 720p, 1080p and 4K (3840x2160) through VA-API,
# compared frame for frame with software decode. Run it after a reboot, without compacting memory first:
# the 1080p hang came from a large kernel allocation failing on fragmented memory (fixed in the usb4.4
# kernel, mseries/fairydust/debian/0003-avd-job-segments-use-kvmalloc.patch).
#
#   bash mseries/check-video-decode.sh [render-node]     needs ffmpeg and vainfo
set -uo pipefail

render=${1:-/dev/dri/renderD128}
for tool in ffmpeg vainfo; do
  command -v "$tool" >/dev/null || { echo "missing $tool" >&2; exit 2; }
done
vainfo --display drm --device "$render" 2>&1 | grep -q VAProfileH264 ||
  { echo "FAIL: no H.264 VA-API profile on $render (reboot once after the firmware is installed)" >&2; exit 1; }

work=$(mktemp -d)
trap 'find "$work" -delete' EXIT
failed=0
for size in 1280x720 1920x1080 3840x2160; do
  clip=$work/$size.mp4
  ffmpeg -v error -f lavfi -i "testsrc2=size=$size:rate=30:duration=2" -pix_fmt yuv420p -c:v libx264 -g 15 "$clip" ||
    { echo "FAIL $size: could not make test clip"; failed=1; continue; }
  soft=$(ffmpeg -v error -i "$clip" -vf format=nv12 -f framemd5 - 2>&1 | grep -v '^#' | awk -F, '{print $NF}' | md5sum)
  if hard=$(timeout 60 ffmpeg -v error -hwaccel vaapi -hwaccel_device "$render" -hwaccel_output_format vaapi \
              -i "$clip" -vf hwdownload,format=nv12 -f framemd5 - 2>"$work/$size.err" | grep -v '^#' | awk -F, '{print $NF}' | md5sum) &&
     [[ $soft == "$hard" ]]; then
    echo "ok       $size hardware decode matches software"
  else
    echo "FAIL     $size hardware decode differs, errored or timed out (see: journalctl -k | grep -i avd)"
    head -3 "$work/$size.err" 2>/dev/null; failed=1
  fi
done
(( failed == 0 )) && echo 'VIDEO DECODE OK' || { echo 'VIDEO DECODE CHECK FAILED' >&2; exit 1; }
