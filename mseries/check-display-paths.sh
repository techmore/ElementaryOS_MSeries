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

# --- connector health -----------------------------------------------------
# link-status Bad means the display coprocessor lost the mode and wants a
# modeset; identical EDIDs on two connected connectors mean a stale dock route.
say ""
say "== Connector health =="
declare -A edid_sum
stale_pair=""
for c in /sys/class/drm/card*/card*-*; do
  [ -e "$c/edid" ] || continue
  name=$(basename "$c")
  [ "$(cat "$c/status" 2>/dev/null)" = connected ] || continue
  # sysfs reports size 0 for the EDID file, so count the bytes actually read.
  [ "$(wc -c <"$c/edid")" -gt 0 ] || continue
  sum=$(md5sum <"$c/edid" | cut -c1-12)
  if [ -n "${edid_sum[$sum]:-}" ]; then
    stale_pair="${edid_sum[$sum]} and $name"
  fi
  edid_sum[$sum]=$name
  kv "$name EDID" "$sum"
done
python3 -I - <<'PY' 2>/dev/null || say "  (link-status unavailable: needs libdrm and read access to /dev/dri)"
import ctypes, glob, os
class Res(ctypes.Structure):
    _fields_ = [("fbs_n", ctypes.c_int), ("fbs", ctypes.c_void_p), ("crtcs_n", ctypes.c_int), ("crtcs", ctypes.c_void_p),
                ("conn_n", ctypes.c_int), ("conn", ctypes.POINTER(ctypes.c_uint32)), ("enc_n", ctypes.c_int),
                ("enc", ctypes.c_void_p), ("a", ctypes.c_uint32), ("b", ctypes.c_uint32), ("c", ctypes.c_uint32), ("d", ctypes.c_uint32)]
class Conn(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("enc", ctypes.c_uint32), ("type", ctypes.c_uint32), ("type_id", ctypes.c_uint32),
                ("connection", ctypes.c_int), ("mmw", ctypes.c_uint32), ("mmh", ctypes.c_uint32), ("sub", ctypes.c_int),
                ("modes_n", ctypes.c_int), ("modes", ctypes.c_void_p), ("props_n", ctypes.c_int),
                ("props", ctypes.POINTER(ctypes.c_uint32)), ("vals", ctypes.POINTER(ctypes.c_uint64))]
class Enum(ctypes.Structure):
    _fields_ = [("v", ctypes.c_uint64), ("n", ctypes.c_char * 32)]
class Prop(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("flags", ctypes.c_uint32), ("name", ctypes.c_char * 32), ("nv", ctypes.c_int),
                ("v", ctypes.c_void_p), ("ne", ctypes.c_int), ("e", ctypes.POINTER(Enum))]
lib = ctypes.CDLL("libdrm.so.2")
lib.drmModeGetResources.restype = ctypes.POINTER(Res)
lib.drmModeGetConnector.restype = ctypes.POINTER(Conn)
lib.drmModeGetProperty.restype = ctypes.POINTER(Prop)
kinds = {10: "DP", 11: "HDMI-A", 14: "eDP"}
bad = False
for node in sorted(glob.glob("/dev/dri/card*")):
    try:
        fd = os.open(node, os.O_RDWR)
    except OSError:
        continue
    res = lib.drmModeGetResources(fd)
    if not res:
        continue
    for i in range(res.contents.conn_n):
        c = lib.drmModeGetConnector(fd, res.contents.conn[i]).contents
        if c.connection != 1:
            continue
        for k in range(c.props_n):
            p = lib.drmModeGetProperty(fd, c.props[k]).contents
            if p.name == b"link-status":
                value = next((p.e[j].n.decode() for j in range(p.ne) if p.e[j].v == c.vals[k]), str(c.vals[k]))
                print(f"  {os.path.basename(node)}-{kinds.get(c.type, c.type)}-{c.type_id} link-status".ljust(36), value)
                bad = bad or value == "Bad"
if bad:
    print("  [BAD]  a connected link reports Bad: the display needs a modeset to retrain.")
PY
if [ -n "$stale_pair" ]; then
  say "  [STALE] $stale_pair are connected with byte-identical EDIDs."
  say "         -> One is a leftover after the dock moved Type-C ports; the compositor"
  say "            ignores the one with the older EDID (updated pantheon-compositor);"
  say "            until it is deployed, a reboot with the dock attached clears it."
fi

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

if [ "${dp_conn:-}" ]; then
  say "  [LIVE] Dock video (WD22TB4 HDMI/DP): a DisplayPort tunnel is up on $dp_conn."
else
  say "  [--]   Dock video (WD22TB4 HDMI/DP): no tunnel connector is connected right now."
fi

say ""
say "== Next action =="
if [ "${hdmi_conn:-}" ] || [ "${dp_conn:-}" ]; then
  say "  A display is live. If it is not lighting up, check its input source."
else
  say "  1) Plug the monitor into the Mac's built-in HDMI port (supported), or"
  say "  2) Use a direct USB-C->HDMI/DP adapter on the front-left USB-C port."
  say "  Re-run this script after plugging in to confirm 'connected'."
fi
