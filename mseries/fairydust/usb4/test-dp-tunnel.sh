#!/usr/bin/env bash
# test-dp-tunnel.sh — collect the evidence for the USB4 DP-tunnel experiment
# (see DP-TUNNEL-RE.md). Read-only: it prints state and a verdict, changes
# nothing. Run:  bash mseries/fairydust/usb4/test-dp-tunnel.sh
#
# Optional follow-up to force the display controller to drive the DP IN adapter:
#   echo 1 | sudo tee /sys/kernel/debug/dri/*/*DP-1/force_link
set -u

say() { printf '%s\n' "$*"; }
kv()  { printf '  %-30s %s\n' "$1" "$2"; }
hr()  { say "------------------------------------------------------------"; }

kver=$(uname -r)
say "== Host =="
kv "kernel" "$kver"
kv "cmdline" "$(tr ' ' '\n' </proc/cmdline | grep -E 'allow_dp_tunnel' || echo '(no allow_dp_tunnel)')"

say ""; say "== thunderbolt module parameter =="
if [ -r /sys/module/thunderbolt/parameters/allow_dp_tunnel ]; then
	kv "allow_dp_tunnel" "$(cat /sys/module/thunderbolt/parameters/allow_dp_tunnel)"
else
	kv "allow_dp_tunnel" "ABSENT (not the experimental kernel, or thunderbolt builtin)"
fi

say ""; say "== Device-tree wiring =="
dt_mux="$(xxd -p /proc/device-tree/soc/dcp@28cc00000/mux-controls 2>/dev/null)"
# mux-controls is <phandle cells...>; last 4 bytes are the mux control index.
idx="?"
[ -n "$dt_mux" ] && idx=$((16#${dt_mux: -8}))
kv "dcpext1 mux-controls idx" "$idx  (0=dpphy 1=dpin0 2=dpin1)"
kv "dcpext1 mux-index" "$(xxd -p /proc/device-tree/soc/dcp@28cc00000/mux-index 2>/dev/null | sed 's/^/0x/')"
for x in 130304c000 b0304c000; do
	[ -d "/proc/device-tree/soc/mux@$x" ] && \
		kv "crossbar $x" "$(tr -d '\0' < /proc/device-tree/soc/mux@$x/status 2>/dev/null)"
done

say ""; say "== DRM connectors =="
for c in /sys/class/drm/card*/card*-*; do
	[ -e "$c/status" ] || continue
	kv "$(basename "$c")" "$(cat "$c/status")"
done

say ""; say "== USB4 / Thunderbolt =="
if [ -d /sys/bus/thunderbolt/devices ]; then
	for d in /sys/bus/thunderbolt/devices/*/; do
		n=$(basename "$d")
		kv "$n" "$(cat "$d/device_name" 2>/dev/null || echo '-')"
	done
else
	kv "thunderbolt" "no /sys/bus/thunderbolt/devices"
fi

say ""; say "== Crossbar switches this boot =="
journalctl -k -b --no-pager 2>/dev/null | grep -i 'apple-display-crossbar' | tail -n 8 ||
	dmesg 2>/dev/null | grep -i 'apple-display-crossbar' | tail -n 8

say ""; say "== DCP link attempts =="
(logs=$(journalctl -k -b --no-pager 2>/dev/null || dmesg 2>/dev/null)
 printf '%s\n' "$logs" | grep -iE 'dcp_dptx_connect|link complete|DPRX|dp tunnel|DP2HDMI' | tail -n 15)

say ""; say "== Counters =="
logs=$(journalctl -k -b --no-pager 2>/dev/null || dmesg 2>/dev/null)
kv "DPRX read timeout" "$(printf '%s\n' "$logs" | grep -c 'DPRX read timeout')"
kv "dp tunnel lines" "$(printf '%s\n' "$logs" | grep -ci 'dp tunnel')"
kv "dcp_dptx_connect" "$(printf '%s\n' "$logs" | grep -c 'dcp_dptx_connect')"

say ""; say "== force_link handles =="
found=0
for f in /sys/kernel/debug/dri/*/*/force_link; do
	[ -e "$f" ] && { kv "$f" "present"; found=1; }
done
[ "$found" = 1 ] || kv "force_link" "none (debugfs not mounted, or non-experimental kernel)"

hr
say "== Verdict =="
timeouts=$(printf '%s\n' "$logs" | grep -c 'DPRX read timeout')
if [ "${idx:-0}" = 0 ]; then
	say "  Crossbar still routes dcpext1 -> dpphy (DP Alt Mode). Not the tunnel build,"
	say "  or the device tree did not change. Expected idx=1 (dpin0) here."
elif [ "$timeouts" = 0 ]; then
	say "  dcpext1 -> dpin0 and no DPRX timeouts: the DP IN adapter answered."
	say "  Check '== DCP link attempts ==' for a completed link / allocated tunnel."
else
	say "  dcpext1 -> dpin0 but DPRX still timing out ($timeouts)."
	say "  Next: force the DCP to drive --"
	say "    echo 1 | sudo tee /sys/kernel/debug/dri/*/*DP-1/force_link"
	say "  then re-run this script. If timeouts persist, try the dpin1 route"
	say "  (<&atcphy1_xbar 2> in t600x-j314-j316.dtsi, DP-TUNNEL-RE.md section 6)."
fi
