#!/usr/bin/env bash
# bench.sh <process-name> [seconds]
# Sums RSS over every process whose comm matches <process-name> and averages
# CPU% over the sampling window (default 20 s) from /proc/<pid>/stat deltas.
# Prints a Markdown table. Electron apps name all their helpers after the
# main binary, so matching by name covers the whole app; set BENCH_TREE=1 to
# also include descendants with other names (for example the claude CLI
# sessions that claude-desktop spawns, or the claude subprocess this client
# runs while a reply streams).
set -euo pipefail
name=${1:?usage: bench.sh <process-name> [seconds]}
window=${2:-20}
tick=$(getconf CLK_TCK)

tree_pids() {
    local roots pid out=""
    roots=$(pgrep -x "$name" || true)
    [ -n "$roots" ] || { echo ""; return; }
    if [ "${BENCH_TREE:-0}" != "1" ]; then echo "$roots"; return; fi
    local queue=($roots)
    while [ ${#queue[@]} -gt 0 ]; do
        pid=${queue[0]}; queue=("${queue[@]:1}")
        out="$out $pid"
        for child in $(pgrep -P "$pid" || true); do queue+=("$child"); done
    done
    echo "$out" | tr ' ' '\n' | grep -v '^$' | sort -un
}

cpu_ticks() { # sum utime+stime over the given pids
    local total=0 pid
    for pid in "$@"; do
        [ -r /proc/$pid/stat ] || continue
        # fields 14 and 15, after the ")" that ends comm
        read -r u s < <(sed 's/^.*) //' /proc/$pid/stat | awk '{print $12, $13}')
        total=$((total + u + s))
    done
    echo "$total"
}

rss_kb() {
    local total=0 pid
    for pid in "$@"; do
        [ -r /proc/$pid/status ] || continue
        total=$((total + $(awk '/^VmRSS:/{print $2}' /proc/$pid/status)))
    done
    echo "$total"
}

pids=($(tree_pids))
if [ ${#pids[@]} -eq 0 ]; then echo "No process named '$name' is running." >&2; exit 1; fi
t0=$(cpu_ticks "${pids[@]}")
rss_sum=0; samples=0; rss_max=0
for ((i = 0; i < window; i++)); do
    sleep 1
    pids=($(tree_pids))
    r=$(rss_kb "${pids[@]}")
    rss_sum=$((rss_sum + r)); samples=$((samples + 1))
    [ "$r" -gt "$rss_max" ] && rss_max=$r
done
t1=$(cpu_ticks "${pids[@]}")
cpu=$(awk -v d=$((t1 - t0)) -v w=$window -v t=$tick 'BEGIN{printf "%.1f", d * 100 / (w * t)}')
avg_mb=$(awk -v k=$rss_sum -v n=$samples 'BEGIN{printf "%.0f", k / n / 1024}')
max_mb=$(awk -v k=$rss_max 'BEGIN{printf "%.0f", k / 1024}')
echo "| Process | Processes | RSS avg (MB) | RSS peak (MB) | CPU % avg over ${window}s |"
echo "|---|---|---|---|---|"
echo "| $name | ${#pids[@]} | $avg_mb | $max_mb | $cpu |"
