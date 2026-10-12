#!/usr/bin/env bash
# verify.sh — run AFTER booting the Fairydust kernel. One OK/FAIL per block.
# Adapted from Grzegorz Smajdor's kit (GPL-2.0); Touch Bar check dropped
# (M1 Pro 14"/16" have none).
set -u

failed=0
check() {
  local label=$1; shift
  if "$@" >/dev/null 2>&1; then printf 'OK   %s\n' "$label"
  else printf 'FAIL %s\n' "$label"; failed=1; fi
}

check "Fairydust kernel booted"      grep -q fairydust /proc/sys/kernel/osrelease
check "Apple GPU DRM device"         sh -c 'find /sys/class/drm -maxdepth 1 -name "card*" | grep -q .'
check "Built-in display (eDP)"       sh -c 'find /sys/class/drm -maxdepth 1 -name "*-eDP-*" | grep -q .'
check "DisplayPort connector (DP-*)" sh -c 'find /sys/class/drm -maxdepth 1 -name "*-DP-*" | grep -q .'
check "USB-C Type-C bus"             test -d /sys/bus/typec/devices
check "Wi-Fi interface"              sh -c 'find /sys/class/net -maxdepth 1 -name "wl*" | grep -q .'
check "FaceTime camera"              test -e /dev/video0
check "Laptop backlight"             test -e /sys/class/backlight/apple-panel-bl/brightness
check "Audio card"                   test -e /proc/asound/cards

printf '\nKernel: '; uname -r
printf 'Model:  '; tr '\0' '\n' </proc/device-tree/model 2>/dev/null || true
printf 'DRM connectors: '; (ls /sys/class/drm/ | grep -E 'card[0-9]+-(DP|HDMI|eDP)' | tr '\n' ' ') || true
printf '\n'

if (( failed )); then
  echo "Some checks failed. The DP connector is the fairydust one; the rest"
  echo "should match stock linux-asahi."
fi
exit "$failed"
