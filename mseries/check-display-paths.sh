#!/usr/bin/env bash
# check-display-paths.sh — report which external-display paths are usable on
# this Mac (Apple Silicon / fairydust-usb4) and what to do next.
#
# Read-only. No root, no writes. Run:  bash mseries/check-display-paths.sh
#
# Background (2026-10-14, verified against source):
#   - Built-in HDMI port is the supported external path on the 14/16" M1 Pro
#     (Asahi feature table: "HDMI Out: linux-asahi (13.5 FW only)").
#   - DP Alt Mode over USB-C is WIP (fairydust); it works for a *direct*
#     USB-C->HDMI/DP adapter on the one "blessed" port, NOT for a
#     Thunderbolt/USB4 dock (chaos_princess: "tb hubs will not work with
#     fairydust, as it is configured to output to dp phy, not to tb interface").
#   - Dock video (HDMI or DP on the WD22TB4) needs USB4 DisplayPort
#     tunnelling, which is not implemented upstream.
set -u

say() { printf '%s\n' "$*"; }
kv()  { printf '  %-34s %s\n' "$1" "$2"; }

kver=$(uname -r)
say "== Host =="
kv "kernel" "$kver"
if [ -r /proc/device-tree/model ]; then
  kv "model" "$(tr -d '\0' </proc/device-tree/model)"
fi

# DCP firmware version (external HDMI/DP path needs 13.5 on the 14/16" M1 Pro).
# apple,firmware-compat is two big-endian u32s: major, minor.
fw=""
for dt in /proc/device-tree/soc/dcp@*; do
  [ -r "$dt/apple,firmware-compat" ] || continue
  raw=$(xxd -p "$dt/apple,firmware-compat" 2>/dev/null)
  if [ -n "$raw" ]; then
    major=$((16#${raw:0:8})); minor=$((16#${raw:8:8}))
    fw="$major.$minor"
  fi
  break
done
kv "DCP firmware-compat" "${fw:-unknown}"

say ""
say "== Kernel support modules =="
mod_state() { if grep -q "^$1 " /proc/modules 2>/dev/null; then echo "loaded"; elif modinfo "$1" >/dev/null 2>&1; then echo "available (not loaded)"; else echo "MISSING"; fi; }
kv "typec_displayport"   "$(mod_state typec_displayport)"
kv "typec_thunderbolt"   "$(mod_state typec_thunderbolt)"
kv "mux_apple_display_crossbar" "$(mod_state mux_apple_display_crossbar)"
kv "phy_apple_atc"       "$(mod_state phy_apple_atc)"

say ""
say "== DRM connectors =="
declare -A st
for c in /sys/class/drm/card*/card*-*; do
  [ -e "$c/status" ] || continue
  name=$(basename "$c")
  st[$name]=$(cat "$c/status")
  kv "$name" "${st[$name]}"
done

# --- verdicts -------------------------------------------------------------
say ""
say "== Verdict =="

has_edp=0; hdmi=0; dp=0
for n in "${!st[@]}"; do
  case "$n" in
    *-eDP-*)  [ "${st[$n]}" = connected ] && has_edp=1 ;;
    *-HDMI-*) hdmi=1; [ "${st[$n]}" = connected ] && hdmi_conn=$n ;;
    *-DP-*)   dp=1;  [ "${st[$n]}" = connected ] && dp_conn=$n ;;
  esac
done

if [ "${hdmi_conn:-}" ]; then
  say "  [LIVE] Built-in HDMI: a display is connected on $hdmi_conn."
elif [ "$hdmi" = 1 ]; then
  say "  [OK]   Built-in HDMI port present ($fw FW). This is the supported path."
  say "         -> Plug the monitor into the Mac's HDMI port. No RE needed."
else
  say "  [??]   No HDMI connector exposed on this machine."
fi

if [ "${dp_conn:-}" ]; then
  say "  [LIVE] USB-C DP Alt Mode: display connected on $dp_conn."
elif [ "$dp" = 1 ]; then
  say "  [WIP]  USB-C DP Alt Mode connector exists but is disconnected."
  say "         -> Works only with a *direct* USB-C->HDMI/DP adapter on the"
  say "            front-left USB-C port. A Thunderbolt dock will NOT work."
else
  say "  [NO]   No DP connector; fairydust DP-altmode not active on this build."
fi

say "  [DEAD] Dock video (WD22TB4 HDMI/DP): needs USB4 DP tunnelling (unimplemented)."

say ""
say "== Next action =="
if [ "${hdmi_conn:-}" ] || [ "${dp_conn:-}" ]; then
  say "  A display is live. If it is not lighting up, check its input source."
else
  say "  1) Plug the monitor into the Mac's built-in HDMI port (supported), or"
  say "  2) Use a direct USB-C->HDMI/DP adapter on the front-left USB-C port."
  say "  Re-run this script after plugging in to confirm 'connected'."
fi
