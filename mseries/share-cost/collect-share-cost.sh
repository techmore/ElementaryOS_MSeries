#!/usr/bin/env bash
# Measure what a live screen share costs THIS desktop: the owner's browser (which
# encodes one WebRTC stream per viewer), the share server, the panel/compositor,
# the PipeWire capture path, and whole-system power when the SMC sensor exists.
#
#   bash mseries/share-cost/collect-share-cost.sh <duration-seconds> <workload-label> <viewers> [interval-seconds]
#   bash mseries/share-cost/collect-share-cost.sh 60 fullscreen-video 1 5
#   bash mseries/share-cost/collect-share-cost.sh 60 fullscreen-video 3 5 --browser brave --require-live
#
# Read-only. It never starts, stops or touches a share, the share server, the
# portal or PipeWire; it only reads /proc, hwmon and the share launcher's
# state.json. It cannot tell whether a viewer consented to anything, and it does
# not try to: viewer counts are read from the launcher's own state file, which
# counts pending and admitted viewers together. Confirm admission separately
# before treating a 3-viewer arm as valid.
#
# The point of the run is a MATCHED PAIR: the same machine, display, content and
# interval with 1 viewer and again with 3. One capture proves nothing; see
# README.md for the protocol and what counts as a result.
set -euo pipefail

usage() {
  awk 'NR > 1 { if ($0 ~ /^#/) { sub(/^# ?/, ""); print; next } exit }' "$0" >&2
  exit 2
}

[[ $# -ge 3 && $# -le 6 ]] || usage
duration=$1
workload=$2
viewers=$3
shift 3
interval=5
browser=brave
require_live=0
while [[ $# -gt 0 ]]; do
  case $1 in
    --browser) browser=${2:?--browser needs a process name}; shift 2 ;;
    --require-live) require_live=1; shift ;;
    *) [[ $1 =~ ^[1-9][0-9]*$ ]] || usage; interval=$1; shift ;;
  esac
done
[[ $duration =~ ^[1-9][0-9]*$ ]] || usage
[[ $interval =~ ^[1-9][0-9]*$ ]] || usage
[[ $workload != *,* && $workload != *$'\n'* ]] || usage
[[ $viewers =~ ^[0-9]+$ ]] || usage
(( duration >= interval )) || usage

state_file="${XDG_RUNTIME_DIR:-/tmp}/rupert-share/state.json"

# Roles are matched in order; the first match wins. "browser" is the owner's
# sharing browser; keep the list to what this machine actually uses so unrelated
# browsers do not silently join the sample.
process_list() {
  ps -eo pid=,comm=,args= | awk -v browser="$browser" '
    # The server binary only: matching any path under rupert-share/core would
    # also catch the launcher shell and the state poller.
    $2 == "rupert-core" || $0 ~ /(^|[[:space:]\/])rupert-core([[:space:]]|$)/ { print $1, $2, "server"; next }
    $2 ~ /^io\.elementary\.(wingpanel|dock)$/ || $2 == "ShareEyes" || $2 == "mseries-share-start" { print $1, $2, "panel"; next }
    $2 == "gala" || $2 == "mseries-gala" || $2 == "pantheon-compositor" || $0 ~ /\/pantheon-compositor( |$)/ { print $1, $2, "compositor"; next }
    $2 ~ /^(pipewire|wireplumber|xdg-desktop-portal|xdg-desktop-portal-gtk|xdg-desktop-portal-pantheon)$/ { print $1, $2, "pipewire"; next }
    # comm is truncated at 15 characters, so the elementary clients are matched
    # on their full path in args as well (the session collector does the same).
    $2 ~ /^io\.elementary\.(wingpanel|dock)/ || $0 ~ /(^|[[:space:]\/])io\.elementary\.(wingpanel|dock)([[:space:]]|$)/ \
      || $2 == "ShareEyes" || $0 ~ /(^|[[:space:]\/])ShareEyes([[:space:]]|$)/ \
      || $0 ~ /(^|[[:space:]\/])mseries-share-start([[:space:]]|$)/ { print $1, $2, "panel"; next }
    $2 == browser || $2 ~ /^(brave|brave-bin|chromium|chromium-browser|google-chrome|google-chrome-stable|firefox|msedge)$/ { print $1, $2, "browser"; next }
  ' | sort -n -u
}

read_ticks() {
  local pid=$1 rest
  [[ -r /proc/$pid/stat ]] || return 1
  # Strip pid and parenthesized comm; utime and stime are then fields 12 and 13.
  rest=$(sed -E 's/^[0-9]+ \(.*\) //' "/proc/$pid/stat") || return 1
  local -a fields
  read -r -a fields <<< "$rest"
  (( ${#fields[@]} >= 13 )) || return 1
  echo $((fields[11] + fields[12]))
}

read_rss_kib() {
  awk '/^VmRSS:/ { print $2; found=1 } END { if (!found) print 0 }' "/proc/$1/status" 2>/dev/null || echo 0
}

# Whole-system power from the SMC "Total System Power" rail, in watts, when the
# Asahi SMC hwmon node exposes it. The rail lives on the node literally named
# macsmc_hwmon; macsmc_battery reports battery flow instead and must not be read
# as system power. NA when it does not exist (or off M-series).
system_power_w() {
  local input name value
  for input in /sys/class/hwmon/*/power1_input; do
    [[ -r $input ]] || continue
    name=$(cat "$(dirname "$input")/name" 2>/dev/null || true)
    [[ $name == macsmc_hwmon ]] || continue
    value=$(cat "$input")
    echo $(( value / 1000000 ))
    return 0
  done
  echo NA
}

battery_sample() {
  local supply battery="" status=NA power=NA capacity=NA ac_online=NA
  for supply in /sys/class/power_supply/*; do
    [[ -r $supply/type ]] || continue
    case $(<"$supply/type") in
      Battery) battery=$supply ;;
      Mains) [[ -r $supply/online ]] && ac_online=$(<"$supply/online") ;;
    esac
  done
  if [[ -n $battery ]]; then
    [[ -r $battery/status ]] && status=$(<"$battery/status")
    if [[ -r $battery/power_now ]]; then
      power=$(( $(<"$battery/power_now") / 1000 ))
    elif [[ -r $battery/current_now && -r $battery/voltage_now ]]; then
      power=$(( $(<"$battery/current_now") * $(<"$battery/voltage_now") / 1000000000 ))
    fi
    [[ -r $battery/capacity ]] && capacity=$(<"$battery/capacity")
  fi
  echo "$power,$status,$ac_online,$capacity"
}

# The launcher's own view of the share, read-only. live/viewers are NA when the
# launcher is not running, which the collector reports instead of guessing.
share_state() {
  local live=NA viewers=NA
  if [[ -r $state_file ]]; then
    live=$(python3 -I -c "import json;print(json.load(open('$state_file')).get('live','NA'))" 2>/dev/null || echo NA)
    viewers=$(python3 -I -c "import json;print(json.load(open('$state_file')).get('viewers','NA'))" 2>/dev/null || echo NA)
  fi
  echo "$live,$viewers"
}

clock_ticks=$(getconf CLK_TCK)
start_epoch=$(date +%s)
end_epoch=$((start_epoch + duration))
declare -A start_ticks
last_sample_epoch=$start_epoch

if [[ $require_live == 1 ]]; then
  IFS=, read -r live _ < <(share_state)
  [[ $live == True || $live == true ]] || {
    echo "error: no live share in $state_file (--require-live)" >&2
    exit 1
  }
elif [[ ! -r $state_file ]]; then
  echo "warning: $state_file not readable; is the share launcher running? Viewer counts will be NA." >&2
fi

roles_seen=$(process_list | awk '{print $3}' | sort -u | tr '\n' ' ')
[[ -n $roles_seen ]] || { echo "error: no share, browser, panel or compositor processes found" >&2; exit 1; }
echo "sampling roles: $roles_seen" >&2

sample_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '# session=share workload=%s display_mode=%s duration_s=%s interval_s=%s started_utc=%s viewers_expected=%s browser=%s\n' \
  "$workload" "internal-panel" "$duration" "$interval" "$sample_utc" "$viewers" "$browser"
printf 'utc,session,workload,display_mode,pid,process,role,cpu_percent_one_core,ram_kib,elapsed_s,system_power_w,battery_flow_mw,battery_status,ac_online,battery_percent,share_live,share_viewers\n'

while read -r pid comm role; do
  [[ -n ${pid:-} ]] || continue
  if ticks=$(read_ticks "$pid"); then
    start_ticks[$pid]=$ticks
  fi
done < <(process_list)

sleep "$interval"
while :; do
  now=$(date +%s)
  elapsed=$((now - start_epoch))
  power=$(system_power_w)
  battery=$(battery_sample)
  IFS=, read -r battery_power battery_status ac_online battery_percent <<< "$battery"
  IFS=, read -r live viewers_now < <(share_state)
  sample_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  while read -r pid comm role; do
    [[ -n ${pid:-} ]] || continue
    ticks=$(read_ticks "$pid") || continue
    if [[ -v start_ticks[$pid] ]]; then
      delta=$((ticks - start_ticks[$pid]))
      cpu=$(awk -v d="$delta" -v h="$clock_ticks" -v i="$((now - last_sample_epoch))" 'BEGIN { printf "%.2f", d * 100 / h / i }')
    else
      # A new PID appeared during sampling, which can indicate a restart.
      cpu=NA
    fi
    rss=$(read_rss_kib "$pid")
    printf '%s,share,%s,internal-panel,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "$sample_utc" "$workload" "$pid" "$comm" "$role" "$cpu" "$rss" "$elapsed" \
      "$power" "$battery_power" "$battery_status" "$ac_online" "$battery_percent" "$live" "$viewers_now"
    start_ticks[$pid]=$ticks
  done < <(process_list)
  (( now >= end_epoch )) && break
  last_sample_epoch=$now
  remaining=$((end_epoch - now))
  sleep_for=$interval
  (( remaining < sleep_for )) && sleep_for=$remaining
  sleep "$sleep_for"
done
