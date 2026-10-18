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
[[ $dur =~ ^[1-9][0-9]*$ ]] || { echo 'duration must be a positive integer' >&2; exit 2; }
sys=${MSERIES_SYS:-/sys}
hw=
for label in "$sys"/class/hwmon/hwmon*/power*_label; do
  [[ -r $label ]] || continue
  case $(tr '[:upper:]' '[:lower:]' < "$label") in
    *'total system'*|'system power'|'system total') hw=${label%_label}_input; break ;;
  esac
done
con=

echo "=== appledrm parameters ==="
for p in force_vrr force_vrr_min show_notch enable_verbose_logging; do
  f=$sys/module/appledrm/parameters/$p
  [[ -r $f ]] && echo "  $p = $(cat "$f")" || echo "  $p = (unreadable)"
done
echo "  cmdline: $(grep -o 'appledrm\.[a-z_]*=[^ ]*' /proc/cmdline | tr '\n' ' ')"

echo
echo "=== DCP evidence (dmesg) ==="
sudo dmesg 2>/dev/null | grep -iE 'adaptive_sync|set_digital_out_mode|vrr' | tail -8 \
  || echo "  (no VRR-related DCP lines yet / no sudo)"

echo
echo "=== display state ==="
[[ -e $con ]] || con=$(ls -d "$sys"/class/drm/card*-eDP-1 2>/dev/null | head -1)
echo "  connector : ${con:-none}"
echo "  enabled   : $(cat "$con/enabled" 2>/dev/null)"
echo "  status    : $(cat "$con/status" 2>/dev/null)"
echo "  bright    : $(cat "$sys/class/backlight/apple-panel-bl/brightness" 2>/dev/null)/$(cat "$sys/class/backlight/apple-panel-bl/max_brightness" 2>/dev/null)"
echo "  modes     : $(cat "$con/modes" 2>/dev/null)"
dbg=$(ls -d "$sys"/kernel/debug/dri/*/eDP-1 2>/dev/null | head -1)
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
    function pct(p, k, lo, hi) {
      k = (d-1)*p; lo = int(k)+1; hi = lo < d ? lo+1 : lo
      return v[lo] + (v[hi]-v[lo])*(k-int(k))
    }
    END {
      printf "  n=%d  p10=%.2f W  p50=%.2f W  p90=%.2f W  min=%.2f W  max=%.2f W  mean=%.2f W\n",
             d, pct(0.10)/1000, pct(0.50)/1000, pct(0.90)/1000,
             v[1]/1000, v[d]/1000, s/d/1000
    }'
else
  echo "  ($hw not readable)"
fi
