#!/usr/bin/env bash
# Make the local video clips the profilers play (1080p, 1440p "2K", 2160p "4K"), H.264 High, 30 fps, 240 s.
# Synthetic (ffmpeg testsrc2 + a 440 Hz tone) so macOS and Linux play exactly the same stream without copying
# hundreds of MB between boots. H.264 because it is the codec the Linux AVD driver decodes in hardware today.
#
#   bash mseries/power/macos-baseline/make_test_videos.sh [outdir]    # default ~/Movies on macOS, ~/Videos on Linux
#
# Bitrates are in the range of real streams at each size (YouTube-ish 1080p 8 Mb/s, 1440p 16, 4K 40).
set -euo pipefail

if [[ $# -ge 1 ]]; then out=$1
elif [[ $(uname) == Darwin ]]; then out=$HOME/Movies
else out=$HOME/Videos; fi
mkdir -p "$out"
command -v ffmpeg >/dev/null || { echo "needs ffmpeg (brew install ffmpeg / sudo apt install ffmpeg)" >&2; exit 1; }

make() {  # size label bitrate maxrate bufsize
    local f="$out/test-$2-h264.mp4"
    if [[ -s $f ]]; then echo "have $f"; return; fi
    echo "making $f ..."
    ffmpeg -hide_banner -loglevel error -y \
        -f lavfi -i "testsrc2=size=$1:rate=30" -f lavfi -i "sine=frequency=440:sample_rate=48000" -t 240 \
        -c:v libx264 -preset fast -profile:v high -pix_fmt yuv420p -b:v "$3" -maxrate "$4" -bufsize "$5" \
        -c:a aac -b:a 128k -movflags +faststart "$f.tmp.mp4"
    mv "$f.tmp.mp4" "$f"
}

make 1920x1080 1080p 8M 10M 16M
make 2560x1440 1440p 16M 20M 32M
make 3840x2160 2160p 40M 50M 80M
ls -lh "$out"/test-*-h264.mp4
