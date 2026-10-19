#!/usr/bin/env bash
# Software vs hardware decode cost, headless (no window is ever opened).
#   bash mseries/video-decode/bench-decode.sh CLIPDIR [REPEATS] [MODES]
#   MODES (comma list, default all): mpv-sw,mpv-hw,gst-sw,gst-hw,ff-sw,ff-hw
#
# mpv-*  real-time playback, --vo=null --no-audio; hw = --hwdec=vaapi-copy (AVD via libva v4l2-request)
# gst-*  real-time playback, fpsdisplaysink(fakesink, sync=true); hw = v4l2sl*dec (GStreamer v4l2codecs)
# ff-*   untimed throughput (decode as fast as possible) with ffmpeg -benchmark; hw keeps frames in VA surfaces
#
# Reported per clip and mode, as the median of REPEATS runs:
#   cpu%    (user+sys CPU time of the player process) / wall time, in % of ONE core (1000% = all 10 cores)
#   wall    seconds; for real-time modes compare with the clip length (longer = playback fell behind)
#   drops   frames dropped (mpv: frame-drop-count + decoder-frame-drop-count; gst: fpsdisplaysink dropped)
#   fps     ff-* only: decoded frames per second of wall time
# Limits (say these with the numbers): vo=null/fakesink means no rendering/compositing cost is included;
# hardware decode work done in kernel threads or IRQ context is not charged to the process; other load on
# the machine adds noise (medians help, they do not remove it). Clips are synthetic (make-test-clips.sh).
set -uo pipefail
dir=${1:?usage: bench-decode.sh CLIPDIR [REPEATS] [MODES]}
reps=${2:-5}
modes=${3:-mpv-sw,mpv-hw,gst-sw,gst-hw,ff-sw,ff-hw}
render=${RENDER_NODE:-/dev/dri/renderD128}
work=$(mktemp -d "${TMPDIR:-/tmp}/bench-decode.XXXXXX")
trap 'rm -rf "$work"' EXIT
cat > "$work/report.lua" <<'EOF'
mp.add_hook("on_unload", 50, function()
  io.stderr:write(string.format("MPVREPORT hwdec=%s drops=%d decdrops=%d\n",
    mp.get_property("hwdec-current", "none"), mp.get_property_number("frame-drop-count", 0),
    mp.get_property_number("decoder-frame-drop-count", 0)))
end)
EOF

median() { sort -n | awk '{a[NR]=$1} END{if(NR==0){print "-"; exit} if(NR%2) print a[(NR+1)/2]; else printf "%.2f\n",(a[NR/2]+a[NR/2+1])/2}'; }

gst_sw_dec() { case $1 in h264) echo avdec_h264 ;; hevc) echo avdec_h265 ;; vp9) echo vp9dec ;; esac; }
gst_hw_dec() { case $1 in h264) echo v4l2slh264dec ;; hevc) echo v4l2slh265dec ;; vp9) echo v4l2slvp9dec ;; esac; }

run_one() {  # mode clip codec -> prints "cpu wall drops fps note"
  local mode=$1 clip=$2 codec=$3 t=$work/time out=$work/out dec rc
  case $mode in
    mpv-sw|mpv-hw)
      local hw=no; [[ $mode == mpv-hw ]] && hw=vaapi-copy
      /usr/bin/time -o "$t" -f '%U %S %e' mpv --no-config --really-quiet --vo=null --no-audio --hwdec=$hw \
        --hwdec-codecs=all --vaapi-device="$render" --framedrop=decoder+vo --script="$work/report.lua" "$clip" 2>"$out" >/dev/null
      rc=$?
      local rep; rep=$(grep MPVREPORT "$out" | tail -1)
      local d1 d2 hwc; hwc=$(sed -n 's/.*hwdec=\([^ ]*\).*/\1/p' <<<"$rep"); d1=$(sed -n 's/.* drops=\([0-9]*\).*/\1/p' <<<"$rep"); d2=$(sed -n 's/.*decdrops=\([0-9]*\).*/\1/p' <<<"$rep")
      read -r u s e <"$t"
      echo "$(awk -v u="$u" -v s="$s" -v e="$e" 'BEGIN{printf "%.0f", (u+s)/e*100}') $e $(( ${d1:-0} + ${d2:-0} )) - hwdec=${hwc:-?}$( ((rc)) && echo " rc=$rc")" ;;
    gst-sw|gst-hw)
      if [[ $mode == gst-sw ]]; then dec=$(gst_sw_dec "$codec"); else dec=$(gst_hw_dec "$codec"); fi
      gst-inspect-1.0 "$dec" >/dev/null 2>&1 || { echo "- - - - no-$dec"; return; }
      /usr/bin/time -o "$t" -f '%U %S %e' gst-launch-1.0 -v filesrc location="$clip" ! parsebin ! "$dec" ! \
        fpsdisplaysink video-sink=fakesink text-overlay=false sync=true signal-fps-measurements=false >"$out" 2>&1
      rc=$?
      local drops; drops=$(grep -o 'dropped: [0-9]*' "$out" | tail -1 | grep -o '[0-9]*')
      read -r u s e <"$t"
      echo "$(awk -v u="$u" -v s="$s" -v e="$e" 'BEGIN{printf "%.0f", (u+s)/e*100}') $e ${drops:-?} - $dec$( ((rc)) && echo " rc=$rc")" ;;
    ff-sw|ff-hw)
      local hwargs=(); [[ $mode == ff-hw ]] && hwargs=(-hwaccel vaapi -hwaccel_device "$render" -hwaccel_output_format vaapi)
      local frames; frames=$(ffprobe -v error -count_packets -select_streams v:0 -show_entries stream=nb_read_packets -of csv=p=0 "$clip")
      /usr/bin/time -o "$t" -f '%U %S %e' ffmpeg -nostdin -v error "${hwargs[@]}" -i "$clip" -f null - >"$out" 2>&1
      rc=$?
      read -r u s e <"$t"
      echo "$(awk -v u="$u" -v s="$s" -v e="$e" 'BEGIN{printf "%.0f", (u+s)/e*100}') $e - $(awk -v f="$frames" -v e="$e" 'BEGIN{printf "%.0f", f/e}') ffmpeg$( ((rc)) && echo " rc=$rc")" ;;
  esac
}

echo "# bench-decode $(date -Is) kernel $(uname -r) reps=$reps"
echo "# load before start: $(cut -d' ' -f1-3 /proc/loadavg)"
printf '%-20s %-7s %6s %7s %6s %6s  %s\n' clip mode cpu% wall drops fps note
for clip in "$dir"/*.mp4 "$dir"/*.webm; do
  [[ -e $clip ]] || continue
  codec=$(ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of csv=p=0 "$clip")
  for mode in ${modes//,/ }; do
    : >"$work/rows"
    for ((i = 0; i < reps; i++)); do run_one "$mode" "$clip" "$codec" >>"$work/rows"; done
    note=$(awk '{ $1=$2=$3=$4=""; print }' "$work/rows" | sort | uniq -c | sed 's/^ *//; s/  */ /g' | paste -sd';')
    printf '%-20s %-7s %6s %7s %6s %6s  %s\n' "$(basename "$clip")" "$mode" \
      "$(cut -d' ' -f1 "$work/rows" | grep -v -- - | median)" "$(cut -d' ' -f2 "$work/rows" | grep -v -- - | median)" \
      "$(cut -d' ' -f3 "$work/rows" | grep -v -- '[-?]' | median)" "$(cut -d' ' -f4 "$work/rows" | grep -v -- - | median)" "$note"
  done
done
echo "# load at end: $(cut -d' ' -f1-3 /proc/loadavg)"
