#!/usr/bin/env bash
# test-dp-tunnel.sh — collect the evidence for the USB4 DP-tunnel experiments
# (see DP-TUNNEL-RE.md and EXP2-RUNBOOK.md). Read-only: it prints state and a
# verdict and changes nothing.
#
#   bash mseries/fairydust/usb4/test-dp-tunnel.sh
#
# Experiment 2 adds two runtime knobs this script reports:
#   * dprx_bypass  — skip the DPRX_DONE wait (the wall experiment 1 hit)
#   * force_link   — per-connector debugfs handle to make the DCP drive the link
set -u

say() { printf '%s\n' "$*"; }
kv()  { printf '  %-34s %s\n' "$1" "$2"; }
hr()  { say "------------------------------------------------------------"; }
param() { # name default
	if [ -r "/sys/module/thunderbolt/parameters/$1" ]; then
		cat "/sys/module/thunderbolt/parameters/$1"
	else
		printf '%s' "$2"
	fi
}

kver=$(uname -r)
say "== Host =="
kv "kernel" "$kver"
kv "budget (boot params)" "$(tr ' ' '\n' </proc/cmdline | grep -E 'thunderbolt' | paste -sd' ' - || echo '(none)')"

say ""; say "== thunderbolt module parameters =="
if [ -r /sys/module/thunderbolt/parameters/allow_dp_tunnel ]; then
	kv "allow_dp_tunnel" "$(param allow_dp_tunnel -)"
	kv "dprx_timeout" "$(param dprx_timeout -)"
	kv "dprx_bypass" "$(param dprx_bypass -)   (1 = skip the DPRX_DONE wait)"
else
	kv "allow_dp_tunnel" "ABSENT (not the experimental kernel)"
fi

say ""; say "== Device-tree wiring (live tree) =="
dt=/proc/device-tree/soc/dcp@28cc00000
dt_mux="$(xxd -p "$dt/mux-controls" 2>/dev/null)"
idx="?"
[ -n "$dt_mux" ] && idx=$((16#${dt_mux: -8}))
kv "dcpext1 mux-controls idx" "$idx  (0=dpphy 1=dpin0 2=dpin1)"
kv "dcpext1 mux-index" "$(xxd -p "$dt/mux-index" 2>/dev/null | sed 's/^/0x/')"
if [ -e "$dt/apple,dp-tunnel" ]; then
	kv "apple,dp-tunnel" "PRESENT (experiment 2: DCP leaves the ATC PHY alone)"
else
	kv "apple,dp-tunnel" "absent (experiment 1 behaviour: DCP attaches atcphy1)"
fi
kv "dcp@289c00000 (HDMI) idx" \
	"$((16#$(xxd -p /proc/device-tree/soc/dcp@289c00000/mux-controls 2>/dev/null | tail -c 9)))  (must stay 0)"

say ""; say "== DRM connectors =="
for c in /sys/class/drm/card*/card*-*; do
	[ -e "$c/status" ] || continue
	kv "$(basename "$c")" "$(cat "$c/status")"
done

say ""; say "== USB4 / Thunderbolt =="
found_dev=0
for d in /sys/bus/thunderbolt/devices/*/; do
	[ -e "$d/device_name" ] || continue
	found_dev=1
	kv "$(basename "$d")" "$(cat "$d/device_name" 2>/dev/null || echo '-')"
done
[ "$found_dev" = 1 ] || kv "thunderbolt" "no devices attached (dock not plugged in?)"

logs=$(journalctl -k -b --no-pager 2>/dev/null || dmesg 2>/dev/null)

say ""; say "== Crossbar switches this boot =="
printf '%s\n' "$logs" | grep -i 'apple-display-crossbar' | tail -n 8

say ""; say "== Tunnel bring-up this boot (last 20) =="
printf '%s\n' "$logs" \
	| grep -v 'Kernel command line' \
	| grep -iE 'DP IN|DP OUT|DPRX|dp tunnel|activating|activation complete|deactivat' \
	| tail -n 20

say ""; say "== DCP link attempts =="
printf '%s\n' "$logs" | grep -iE 'dcp_dptx_connect|dcp_dptx_disconnect|link complete|DP2HDMI|DCP index' | tail -n 12

say ""; say "== DCP DPTXPort calls (DCP firmware -> driver) =="
# The DCP firmware owns sink detection on the tunnelled path: it asks the driver
# for link parameters and reports sink state. Call numbers (dptxep.h):
#   5/6 will/did change link config   7/8/9 link rate   10/11/12 lanes
#   18 supports HPD   19 force hotplug detect   20 INACTIVE_SINK_DETECTED
#   21 tiled display hints   22/23/24 device not responding / busy / not started
printf '%s\n' "$logs" | grep -oE 'acking unhandled call [0-9]+|DPINDBG apcall idx=[0-9]+' \
	| awk '{print $NF}' | sed 's/idx=//' \
	| sort -n | uniq -c | awk '{printf "  call %-3s x%s\n", $2, $1}'
printf '%s\n' "$logs" | grep -i 'DPTXPort:' | tail -n 8

say ""; say "== Counters =="
kv "DPRX read timeout" "$(printf '%s\n' "$logs" | grep -c 'DPRX read timeout')"
kv "DPRX bypass engaged" "$(printf '%s\n' "$logs" | grep -c 'DPRX bypass enabled')"
kv "Video/AUX path activation complete" "$(printf '%s\n' "$logs" | grep -c 'activation complete')"
kv "dcp_dptx_connect(port=0)" "$(printf '%s\n' "$logs" | grep -cE 'dcp_dptx_connect\(port=0\)|dcp_dptx_connect_source')"

say ""; say "== force_link handles (experiment 2 / experiment 1 builds) =="
found=0
while IFS= read -r f; do
	[ -e "$f" ] || continue
	kv "$f" "present"; found=1
done < <(find /sys/kernel/debug/dri -name force_link 2>/dev/null)
[ "$found" = 1 ] || kv "force_link" "none (needs sudo, or non-experimental kernel)"

hr
say "== Verdict =="
timeouts=$(printf '%s\n' "$logs" | grep -c 'DPRX read timeout')
activations=$(printf '%s\n' "$logs" | grep -c 'activation complete')
connect=$(printf '%s\n' "$logs" | grep -cE 'dcp_dptx_connect\(port=0\)|dcp_dptx_connect_source')
# dprx_bypass sysfs reports Y/N (the boot parameter is 1/0); accept both.
bypass="$(param dprx_bypass 0)"
case "$bypass" in 1|[Yy]) bypass_on=1 ;; *) bypass_on=0 ;; esac
# External connectors only: the built-in eDP is always connected and must not
# turn "paths activated" into a display-success verdict.
connected=$(for c in /sys/class/drm/card*/card*-DP-* /sys/class/drm/card*/card*-HDMI-*; do
	[ -e "$c/status" ] && cat "$c/status"
done 2>/dev/null | grep -c '^connected$')
inactive=$(printf '%s\n' "$logs" | grep -cE 'acking unhandled call 20|DPINDBG apcall idx=20')
# patches 0012/0013: the DP-IN-to-DCP bridge now runs automatically and logs
# the tunnel source connect directly. Prefer this over the legacy wording.
src=$(printf '%s\n' "$logs" | grep -o 'DPINDBG connect_source: waited=[0-9]* ret=-*[0-9]*' | tail -n 1)

if [ -n "$src" ]; then
	say "  DPINDBG tunnel source connect: $src"
	if printf '%s\n' "$src" | grep -q 'ret=0'; then
		say "  ret=0 — the DCP configured the link. If no external connector above is"
		say "  connected, the remaining problem is a mode set, not the link."
	elif printf '%s\n' "$src" | grep -q 'ret=-67'; then
		say "  ret=-67 (-ENOLINK). In tunnel mode the driver maps the firmware's"
		say "  calls 22/24/20 (DEVICE_NOT_RESPONDING / NOT_STARTED /"
		say "  INACTIVE_SINK_DETECTED) to -ENOLINK, so this is normally the firmware"
		say "  reporting that the tunnelled sink does not respond — not a"
		say "  firmware-returned error and not a timeout. Work the sink/AUX path"
		say "  (patches 0012/0013). Keep bypass armed before touching any cable."
	elif printf '%s\n' "$src" | grep -q 'ret=-110'; then
		say "  ret=-110 (-ETIMEDOUT). On the tunnel path check for an"
		say "  'E1 set_hpd(1) ... ignored (tunnel)' line (patch 0013): if absent, a"
		say "  tunnel-mode set_hpd failure is still fatal here."
	else
		say "  See the DPINDBG trace above for the failing layer."
	fi
elif [ "${idx:-0}" = 0 ]; then
	say "  Crossbar still routes dcpext1 -> dpphy (DP Alt Mode). The tree is not armed"
	say "  for the tunnel; expected idx=1 (dpin0). Check with boot-dt.py, not the build."
elif [ "$connected" -gt 0 ] && [ "$activations" -gt 0 ]; then
	say "  A connector is CONNECTED and paths activated: the tunnel is up and a display"
	say "  attached. If the panel is still dark, it is a mode-set problem, not a link one."
elif [ "$inactive" -gt 0 ]; then
	say "  The DCP firmware ran its own sink detection on the tunnelled connector and"
	say "  reported INACTIVE_SINK_DETECTED ($inactive x) with $connect dcp_dptx_connect"
	say "  call(s) -- i.e. it probes the DP IN path on its own. It sees no live sink, so"
	say "  the router's DPRX_DONE will never be set. Work the sink: monitor powered and"
	say "  on that exact input, dock's HDMI rather than a DP adapter, or the dock's other"
	say "  output. Watch for calls 5/6/7/9 (link config / link rate): those mean the"
	say "  firmware is actually driving the link."
	say "  EARLY-STOP: a silent sink is the frontier answer. No driver/DT change on this"
	say "  machine can complete a read the router cannot make. Save this output and pivot"
	say "  to the macOS trace (MACOS-TRACE-RUNBOOK.md) rather than patching further."
elif [ "$bypass_on" = 1 ]; then
	say "  dprx_bypass=1 and idx=$idx. If the DPRX storm stopped and the paths report"
	say "  'activation complete', the tunnel is up -- the remaining question is whether"
	say "  the DCP drives the DP IN adapter. Check 'DCP link attempts' for"
	say "  dcp_dptx_connect(port=0); if absent, force it:"
	say "    sudo sh -c 'echo 1 > $(find /sys/kernel/debug/dri -name force_link | head -1)'"
	say "  Note there is one force_link per connector: use the one under DP-1."
elif [ "$timeouts" -gt 100 ]; then
	say "  Crossbar armed (idx=$idx) but a DPRX retry storm is running ($timeouts lines)."
	say "  This is the experiment-1 wall. Arm the bypass *now*, before touching the cable:"
	say "    echo 1 | sudo tee /sys/module/thunderbolt/parameters/dprx_bypass"
elif [ "$activations" -gt 0 ]; then
	say "  Paths activated ($activations) with idx=$idx and no storm. Look at whether the"
	say "  DCP connected ($connect attempt(s)) and whether a connector came up."
else
	say "  Nothing yet: no DP IN/OUT pairing and no tunnel attempt in this boot. Either the"
	say "  dock has no display attached, or the sink port is not the one wired to the ACIO."
	say "  Re-check the monitor is live on the dock's HDMI/DP and that the dock is on USB-C"
	say "  Left Front (atcphy1)."
fi
say ""
say "Hazard: do NOT unplug the dock while a DPRX read is in flight (it deadlocks"
say "apple_nhi_remove and wedges the Type-C port until reboot). Make it safe first by"
say "ARMING the bypass (write 1, not 0) BEFORE touching the cable:"
say "  echo 1 | sudo tee /sys/module/thunderbolt/parameters/dprx_bypass"
