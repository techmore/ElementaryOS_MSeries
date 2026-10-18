#!/bin/bash
# usage: samp.sh N  -> prints median/mean of Total System Power (W) and cpu busy% at 1 Hz
H=/sys/class/hwmon/hwmon2; N=${1:-60}
p=();
read -r _ u n s i w q sq st _ < /proc/stat; t0=$((u+n+s+i+w+q+sq+st)); i0=$((i+w))
for ((k=0;k<N;k++)); do p+=($(cat $H/power1_input)); sleep 1; done
read -r _ u n s i w q sq st _ < /proc/stat; t1=$((u+n+s+i+w+q+sq+st)); i1=$((i+w))
printf '%s\n' "${p[@]}" | sort -n | awk '{a[NR]=$1;s+=$1} END{printf "n=%d median=%.2fW mean=%.2fW min=%.2f max=%.2f ",NR,a[int((NR+1)/2)]/1e6,s/NR/1e6,a[1]/1e6,a[NR]/1e6}'
echo "cpu_busy=$(( (100*((t1-t0)-(i1-i0)))/(t1-t0) ))%"
