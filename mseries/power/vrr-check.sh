#!/usr/bin/env bash
# mseries/power/vrr-check.sh — read-only evidence for the ProMotion / adaptive-sync test.
#
# Prints (no measurements are ever set by this script):
#   * appledrm parameter state (force_vrr / force_vrr_min / show_notch)
#   * DCP evidence from dmesg: set_digital_out_mode(.. vrr:N) and adaptive_sync minRR
#   * the eDP connector's advertised mode + vrr_range
#   * SMC "Total System Power" p10/p50/p90 over DURATION seconds
#
# Usage: ./vrr-check.sh [duration-seconds]     (default 20)
set -uo pipefail

dur=${1:-20}
hw=/sys/class/hwmon/hwmon2/power1_input
con=/sys/class/drm/card2-eDP-1

echo "=== appledrm parameters ==="
for p in force_vrr force_vrr_min show_notch enable_verbose_logging; do
  f=/sys/module/appledrm/parameters/$p
  [[ -r $f ]] && echo "  $p = $(cat "$f")" || echo "  $p = (unreadable)"
done
echo "  cmdline: $(grep -o 'appledrm\.[a-z_]*=[^ ]*' /proc/cmdline | tr '\n' ' ')"

echo
echo "=== DCP evidence (dmesg) ==="
sudo dmesg 2>/dev/null | grep -iE 'adaptive_sync|set_digital_out_mode|vrr' | tail -8 \
  || echo "  (no VRR-related DCP lines yet / no sudo)"

echo
echo "=== display state ==="
[[ -e $con ]] || con=$(ls -d /sys/class/drm/card*-eDP-1 2>/dev/null | head -1)
echo "  connector : ${con:-none}"
echo "  enabled   : $(cat "$con/enabled" 2>/dev/null)"
echo "  status    : $(cat "$con/status" 2>/dev/null)"
echo "  bright    : $(cat /sys/class/backlight/apple-panel-bl/brightness 2>/dev/null)/$(cat /sys/class/backlight/apple-panel-bl/max_brightness 2>/dev/null)"
echo "  modes     : $(cat "$con/modes" 2>/dev/null)"
dbg=$(ls -d /sys/kernel/debug/dri/*/eDP-1 2>/dev/null | head -1)
[[ -n $dbg ]] && echo "  vrr_range : $(cat "$dbg/vrr_range" 2>/dev/null | tr '\n' ' ')"

echo
echo "=== SMC total system power over ${dur}s ==="
if [[ -r $hw ]]; then
  vals=()
  for i in $(seq 1 "$dur"); do
    vals+=("$(( $(cat "$hw") / 1000 ))")   # uW -> mW
    sleep 1
  done
  printf '%s\n' "${vals[@]}" | sort -n | awk -v d=${#vals[@]} '
    { v[NR] = $1; s += $1 }
    END {
      i10 = int(d*0.10) + 1; if (i10 > d) i10 = d
      i50 = int(d*0.50) + 1; if (i50 > d) i50 = d
      i90 = int(d*0.90) + 1; if (i90 > d) i90 = d
      j10 = (i10 < d) ? i10 + 1 : i10
      j90 = (i90 < d) ? i90 + 1 : i90
      printf "  n=%d  p10=%.2f W  p50=%.2f W  p90=%.2f W  min=%.2f W  max=%.2f W  mean=%.2f W\n",
             d, (v[i10] + v[j10]) / 2 / 1000, v[i50] / 1000, (v[i90] + v[j90]) / 2 / 1000,
             v[1] / 1000, v[d] / 1000, s / d / 1000
    }'
else
  echo "  ($hw not readable)"
fi
