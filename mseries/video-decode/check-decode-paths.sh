#!/usr/bin/env bash
# Correctness check of every hardware decode path against software decode, per clip, headless (no window).
#   bash mseries/video-decode/check-decode-paths.sh CLIPDIR       (clips from make-test-clips.sh)
# Paths: ffmpeg VA-API (libva v4l2-request bridge, what mpv/Brave use) and GStreamer v4l2codecs
# (v4l2slh264dec / v4l2slh265dec / v4l2slvp9dec, what GStreamer players such as Videos/Totem would use).
# Each path decodes the whole clip to raw YUV and the md5 is compared with ffmpeg's software decode.
# A pass proves bit-exact decode of these clips; it is not a test of every real-world stream.
set -uo pipefail
dir=${1:?usage: check-decode-paths.sh CLIPDIR}
render=${RENDER_NODE:-/dev/dri/renderD128}
have_gst=0
gst-inspect-1.0 v4l2codecs >/dev/null 2>&1 && have_gst=1
fail=0
printf '%-22s %-6s %-8s %-8s %s\n' clip frames vaapi gst-v4l2 note
for clip in "$dir"/*.mp4 "$dir"/*.webm "$dir"/*.mkv; do
  [[ -e $clip ]] || continue
  codec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$clip")
  pix=$(ffprobe -v error -select_streams v:0 -show_entries stream=pix_fmt -of csv=p=0 "$clip")
  case $pix in *10le) sw=yuv420p10le hw=p010le gfmt=I420_10LE ;; *) sw=yuv420p hw=nv12 gfmt=I420 ;; esac
  case $codec in h264) el=v4l2slh264dec ;; hevc) el=v4l2slh265dec ;; vp9) el=v4l2slvp9dec ;; *) el= ;; esac
  ref=$(ffmpeg -nostdin -v error -i "$clip" -pix_fmt "$sw" -f rawvideo - | md5sum | cut -c1-32)
  frames=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$clip")
  va=$(timeout 120 ffmpeg -nostdin -v error -hwaccel vaapi -hwaccel_device "$render" -hwaccel_output_format vaapi \
        -i "$clip" -vf "hwdownload,format=$hw" -pix_fmt "$sw" -f rawvideo - 2>/dev/null | md5sum | cut -c1-32)
  [[ $va == "$ref" ]] && va=ok || { va=DIFF; fail=1; }
  g=skip
  if (( have_gst )) && [[ -n $el ]]; then
    g=$(timeout 120 gst-launch-1.0 -q filesrc location="$clip" ! parsebin ! "$el" ! videoconvert ! \
          "video/x-raw,format=$gfmt" ! fdsink fd=1 2>/dev/null | md5sum | cut -c1-32)
    [[ $g == "$ref" ]] && g=ok || { g=DIFF; fail=1; }
  fi
  printf '%-22s %-6s %-8s %-8s %s\n' "$(basename "$clip")" "$frames" "$va" "$g" "$codec $pix"
done
(( have_gst )) || echo 'note: GStreamer v4l2codecs not installed (gstreamer1.0-plugins-bad); gst column skipped'
(( fail == 0 )) && echo 'DECODE PATHS OK' || { echo 'DECODE PATH MISMATCH (journalctl -k | grep -i avd)' >&2; exit 1; }
