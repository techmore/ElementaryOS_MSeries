#!/usr/bin/env bash
# bench.sh <pid> [seconds]: average CPU % and average/peak RSS of one process over N seconds from /proc
# (utime+stime deltas from /proc/<pid>/stat, VmRSS from /proc/<pid>/status, sampled once a second).
pid=$1; secs=${2:-20}
hz=$(getconf CLK_TCK)
read -r t0 < <(awk '{print $14+$15}' /proc/$pid/stat)
rss_sum=0; rss_max=0; n=0
for _ in $(seq 1 "$secs"); do
  sleep 1
  rss=$(awk '/VmRSS/{print $2}' /proc/$pid/status)
  rss_sum=$((rss_sum+rss)); n=$((n+1)); [ "$rss" -gt "$rss_max" ] && rss_max=$rss
done
read -r t1 < <(awk '{print $14+$15}' /proc/$pid/stat)
cpu=$(awk -v a=$t0 -v b=$t1 -v hz=$hz -v s=$secs 'BEGIN{printf "%.1f", (b-a)*100/hz/s}')
echo "pid=$pid cpu_avg=${cpu}% rss_avg=$((rss_sum/n/1024))MB rss_peak=$((rss_max/1024))MB over ${secs}s"
