# shellcheck shell=bash
# Per-module timing for the installer runners (#47). Source it; nothing runs on source.
#
#   timing_begin                          note the start time and the CPU used so far
#   timing_end LOG NAME STATUS RC         append one JSON line: start, end, wall and CPU seconds
#   timing_summary LOG [MODE [JSON]]      table sorted by wall time + one summary line
#                                         (and the JSON document when JSON is given)
#
# CPU time is that of the child processes this shell has waited for since
# timing_begin, so run the module as a command (or function that runs commands)
# in this shell, not in a background job. STATUS is ok, failed or not-applicable.
# The log format is the one mseries/modrun.py reads and writes.
#
# Needs bash 5 (EPOCHREALTIME). Everything here is best effort: a timing problem
# never changes what the installer does.

_timing_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Microseconds since the epoch in NOW_US. A variable, not $(...): no subshell.
_timing_now() { local t=${EPOCHREALTIME:-0}; NOW_US=$((10#${t/[.,]/})); }

_timing_clock_ms() { # 1m13.200s -> 73200
  local m=${1%%m*} sec=${1#*m} frac
  sec=${sec%s}; frac=${sec#*.}000
  echo $((10#$m * 60000 + 10#${sec%.*} * 1000 + 10#${frac:0:3}))
}

# `times` has to run in this shell: a command substitution is a new process with no children yet.
_timing_cpu() { # CPU_USER_MS CPU_SYS_MS: children waited for so far
  local f=${TMPDIR:-/tmp}/mseries-times.$$ u=0m0s s=0m0s
  if times >"$f" 2>/dev/null; then { read -r _; read -r u s; } <"$f"; fi
  rm -f "$f"
  CPU_USER_MS=$(_timing_clock_ms "$u"); CPU_SYS_MS=$(_timing_clock_ms "$s")
}

_timing_sec3() { printf '%d.%03d' $(($1 / 1000000)) $(($1 % 1000000 / 1000)); }   # microseconds -> seconds
_timing_ms3() { printf '%d.%03d' $(($1 / 1000)) $(($1 % 1000)); }                 # milliseconds -> seconds

timing_begin() {
  _timing_now; _T0_US=$NOW_US
  _timing_cpu; _U0_MS=$CPU_USER_MS; _S0_MS=$CPU_SYS_MS
}

timing_end() { # timing_end LOG NAME STATUS RC
  local log=$1 name=$2 status=$3 rc=$4
  _timing_now; _timing_cpu
  printf '{"name":"%s","status":"%s","rc":%d,"start":%s,"end":%s,"wall_s":%s,"cpu_user_s":%s,"cpu_sys_s":%s}\n' \
    "$name" "$status" "$rc" "$(_timing_sec3 "$_T0_US")" "$(_timing_sec3 "$NOW_US")" \
    "$(_timing_sec3 $((NOW_US - _T0_US)))" \
    "$(_timing_ms3 $((CPU_USER_MS - _U0_MS)))" "$(_timing_ms3 $((CPU_SYS_MS - _S0_MS)))" >>"$log" 2>/dev/null || true
}

# The scheduler does the table and JSON when python3 and it are present; otherwise a plain sorted list.
timing_summary() { # timing_summary LOG [MODE [JSON]]
  local log=$1 mode=${2:-} json=${3:-} modrun=${MODRUN:-$_timing_dir/modrun.py}
  [[ -s $log ]] || return 0
  if command -v python3 >/dev/null 2>&1 && [[ -f $modrun ]]; then
    python3 "$modrun" summarize --timing-log "$log" ${mode:+--mode "$mode"} ${json:+--summary-json "$json"}
  else
    sed -E 's/.*"name":"([^"]*)".*"wall_s":([0-9.]+).*/\2 \1/' "$log" | sort -rn |
      awk 'BEGIN {printf "timing (slowest first):"} {printf " %s %ss", $2, $1} END {print ""}'
  fi
}
