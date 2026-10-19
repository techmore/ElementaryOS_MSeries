#!/usr/bin/env bash
# Make the synthetic benchmark clips used by bench-decode.sh (no network, no downloads).
#   bash mseries/video-decode/make-test-clips.sh DIR [SECONDS]
# Content is testsrc2 with temporal noise so the encoders cannot cheat on static frames; it is still synthetic,
# so it proves the decode path and gives comparable CPU numbers, not every real-world stream (film grain,
# YouTube's encoder settings, very high bitrates). Encodes run at nice 19 with few threads.
set -euo pipefail
dir=${1:?usage: make-test-clips.sh DIR [SECONDS]}
secs=${2:-10}
mkdir -p "$dir"
src() { echo "testsrc2=size=$1:rate=$2:duration=$secs,noise=alls=10:allf=t+u,format=$3"; }
enc() {  # name size rate pixfmt codec-args...
  local name=$1 size=$2 rate=$3 pix=$4; shift 4
  [[ -s $dir/$name ]] && { echo "have $name"; return; }
  echo "making $name"
  nice -n 19 ffmpeg -nostdin -v error -f lavfi -i "$(src "$size" "$rate" "$pix")" "$@" -an "$dir/$name.part.${name##*.}" &&
    mv "$dir/$name.part.${name##*.}" "$dir/$name"
}
x264=(-c:v libx264 -preset veryfast -profile:v high -threads 4)
x265=(-c:v libx265 -preset ultrafast -x265-params log-level=error:pools=4)
vp9=(-c:v libvpx-vp9 -deadline realtime -cpu-used 8 -row-mt 1 -threads 4 -tile-columns 2)
enc h264-1080p30.mp4  1920x1080 30 yuv420p     "${x264[@]}" -b:v 8M  -maxrate 10M -bufsize 16M -g 60
enc h264-1080p60.mp4  1920x1080 60 yuv420p     "${x264[@]}" -b:v 12M -maxrate 15M -bufsize 24M -g 120
enc h264-2160p30.mp4  3840x2160 30 yuv420p     "${x264[@]}" -b:v 35M -maxrate 40M -bufsize 60M -g 60
enc hevc-1080p30.mp4  1920x1080 30 yuv420p     "${x265[@]}" -b:v 5M -tag:v hvc1 -g 60
enc hevc10-2160p30.mp4 3840x2160 30 yuv420p10le "${x265[@]}" -profile:v main10 -b:v 20M -tag:v hvc1 -g 60
enc vp9-1080p30.webm  1920x1080 30 yuv420p     "${vp9[@]}" -b:v 4M -g 120
enc vp9-1080p60.webm  1920x1080 60 yuv420p     "${vp9[@]}" -b:v 6M -g 240
enc vp9-2160p30.webm  3840x2160 30 yuv420p     "${vp9[@]}" -b:v 18M -g 120
ls -l "$dir"
