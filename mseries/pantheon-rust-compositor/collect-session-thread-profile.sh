#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <gala|rust> <workload-label> <duration-seconds> [interval-seconds]" >&2
  exit 2
}

[[ $# -ge 3 && $# -le 4 ]] || usage
session=$1
workload=$2
duration=$3
interval=${4:-1}
[[ $session == gala || $session == rust ]] || usage
[[ $duration =~ ^[1-9][0-9]*$ && $interval =~ ^[1-9][0-9]*$ ]] || usage
[[ $workload != *','* && $workload != *$'\n'* ]] || usage
(( duration >= interval )) || usage

command -v pidstat >/dev/null || {
  echo "error: pidstat from sysstat is required" >&2
  exit 1
}

mapfile -t pids < <(
  ps -eo pid=,comm=,args= | awk -v session="$session" '
    session == "gala" && ($2 == "gala" || $2 == "mseries-gala") { print $1; next }
    session == "rust" && ($2 == "pantheon-compositor" || $0 ~ /\/pantheon-compositor([[:space:]]|$)/) { print $1; next }
    $2 ~ /^io\.elementary\.(wingpanel|dock)/ || $0 ~ /(^|[[:space:]\/])io\.elementary\.(wingpanel|dock)([[:space:]]|$)/ { print $1 }
  ' | sort -n -u
)

if (( ${#pids[@]} == 0 )); then
  echo "error: no compositor or Pantheon shell processes found for session '$session'" >&2
  exit 1
fi

printf -v pid_list '%s,' "${pids[@]}"
pid_list=${pid_list%,}
samples=$(((duration + interval - 1) / interval))

printf '# session=%s workload=%s started_utc=%s duration_s=%s interval_s=%s pids=%s\n' \
  "$session" "$workload" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$duration" "$interval" "$pid_list"
ps -p "$pid_list" -o pid=,ppid=,comm=,args=
printf '\n## Per-thread CPU and memory samples (pidstat)\n'
LC_ALL=C pidstat -t -u -r -p "$pid_list" "$interval" "$samples"
