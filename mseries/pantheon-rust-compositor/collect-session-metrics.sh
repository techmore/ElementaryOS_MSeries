#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <gala|rust> <duration-seconds> <workload-label> <display-mode> [interval-seconds]" >&2
  exit 2
}

[[ $# -ge 4 && $# -le 5 ]] || usage
session=$1
duration=$2
workload=$3
display_mode=$4
interval=${5:-5}
[[ $session == gala || $session == rust ]] || usage
[[ $duration =~ ^[1-9][0-9]*$ && $interval =~ ^[1-9][0-9]*$ ]] || usage
[[ $workload != *','* && $workload != *$'\n'* && $display_mode != *','* && $display_mode != *$'\n'* ]] || usage
(( duration >= interval )) || usage

clock_ticks=$(getconf CLK_TCK)
start_epoch=$(date +%s)
end_epoch=$((start_epoch + duration))
declare -A start_ticks
last_sample_epoch=$start_epoch

process_list() {
  ps -eo pid=,comm=,args= | awk '
    $2 == "gala" || $2 == "mseries-gala" || $2 == "pantheon-compositor" ||
    $0 ~ /\/pantheon-compositor( |$)/ ||
    $2 ~ /^io\.elementary\.(wingpanel|dock)/ ||
    $0 ~ /\/io\.elementary\.(wingpanel|dock)( |$)/ {
      print $1, $2
    }' | sort -n -u
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

battery_sample() {
  local supply
  for supply in /sys/class/power_supply/BAT*; do
    [[ -d $supply ]] || continue
    local power capacity
    power=NA
    capacity=NA
    if [[ -r $supply/power_now ]]; then
      power=$(( $(<"$supply/power_now") / 1000 ))
    elif [[ -r $supply/current_now && -r $supply/voltage_now ]]; then
      power=$(( $(<"$supply/current_now") * $(<"$supply/voltage_now") / 1000000000 ))
    fi
    [[ -r $supply/capacity ]] && capacity=$(<"$supply/capacity")
    echo "$power,$capacity"
    return
  done
  echo "NA,NA"
}

sample_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf '# session=%s workload=%s display_mode=%s duration_s=%s interval_s=%s started_utc=%s\n' \
  "$session" "$workload" "$display_mode" "$duration" "$interval" "$sample_utc"
printf 'utc,session,workload,display_mode,pid,process,cpu_percent_one_core,ram_kib,elapsed_s,battery_power_mw,battery_percent\n'

while read -r pid comm; do
  [[ -n ${pid:-} ]] || continue
  if ticks=$(read_ticks "$pid"); then
    start_ticks[$pid]=$ticks
  fi
done < <(process_list)

if (( ${#start_ticks[@]} == 0 )); then
  echo "error: no Gala or Rust compositor/shell processes found" >&2
  exit 1
fi

sleep "$interval"
while :; do
  now=$(date +%s)
  elapsed=$((now - start_epoch))
  battery=$(battery_sample)
  battery_power=${battery%,*}
  battery_percent=${battery#*,}
  sample_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  while read -r pid comm; do
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
    printf '%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s\n' \
      "$sample_utc" "$session" "$workload" "$display_mode" "$pid" "$comm" "$cpu" "$rss" "$elapsed" \
      "$battery_power" "$battery_percent"
    start_ticks[$pid]=$ticks
  done < <(process_list)
  (( now >= end_epoch )) && break
  last_sample_epoch=$now
  remaining=$((end_epoch - now))
  sleep_for=$interval
  (( remaining < sleep_for )) && sleep_for=$remaining
  sleep "$sleep_for"
done
