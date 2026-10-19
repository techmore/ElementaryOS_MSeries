#!/usr/bin/env bash
set -euo pipefail

usage() {
  echo "Usage: $0 <gala|rust>" >&2
  exit 2
}

[[ $# -eq 1 ]] || usage
case "$1" in
  gala)
    manager_unit=gnome-session-manager@pantheon-wayland.service
    compositor_unit=io.elementary.gala@wayland.service
    ;;
  rust)
    manager_unit=gnome-session-manager@pantheon-rust-wayland.service
    compositor_unit=pantheon-rust-compositor@wayland.service
    ;;
  *) usage ;;
esac

printf '# session=%s started_utc=%s boot_id=%s\n' \
  "$1" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(cat /proc/sys/kernel/random/boot_id)"
printf '\n## OS boot timing\n'
systemd-analyze time
systemd-analyze critical-chain graphical.target --no-pager || true
systemd-analyze critical-chain display-manager.service --no-pager || true

printf '\n## Slow system units\n'
systemd-analyze blame --no-pager | head -20

printf '\n## Display manager timeline\n'
journalctl -b -u display-manager.service -o short-monotonic --no-pager || true

printf '\n## Session and shell timeline\n'
journalctl --user -b -o short-monotonic --no-pager \
  -u "$manager_unit" \
  -u "$compositor_unit" \
  -u pantheon-wingpanel.service \
  -u pantheon-dock.service \
  -u xdg-desktop-portal.service \
  -u xdg-desktop-portal-pantheon.service \
  -u io.elementary.files.xdg-desktop-portal.service \
  -u xdg-desktop-portal-gnome.service \
  -u org.freedesktop.IBus.session.GNOME.service \
  | grep -Ei 'Starting |Started |Stopped |Reached target |Failed|timed out|skipped|READY|Created new socket|Loaded Keymap|wallpaper|Creating new Output|GL Renderer|drm surface' \
  || true

printf '\n## Current login session\n'
loginctl list-sessions --no-legend
