#!/usr/bin/env bash
# Stop xdg-desktop-portal from making the next login slow after the compositor dies.
#
# When Gala crashed (journal 2026-10-18 21:43:11), an app re-activated xdg-desktop-portal while no
# display existed. The portal waited on the GTK backend, which could not open a display, until its
# 90 s start timeout. That queued start job made gnome-session's "restart D-Bus after shutdown" step fail
# (TransactionIsDestructive), so stale services from the dead session survived into the next login,
# and apps there blocked on 25 s "Timeout was reached" portal calls for about two minutes.
# This drop-in makes the portal refuse to start while no Wayland display is exported; the start job
# then ends at once and the D-Bus restart can run. A normal session always exports WAYLAND_DISPLAY
# before apps ask for the portal, so behaviour is otherwise unchanged.
#
#   bash mseries/install-portal-relogin-fix.sh              # install (this user only, no root)
#   bash mseries/install-portal-relogin-fix.sh --uninstall  # remove
# DESTDIR=/some/root is honoured for testing.
set -euo pipefail
dir="${DESTDIR:-$HOME/.config}/systemd/user/xdg-desktop-portal.service.d"
file="$dir/10-mseries-need-display.conf"
if [[ ${1:-} == --uninstall ]]; then
  rm -f "$file"
  rmdir "$dir" 2>/dev/null || true
  [[ -n ${DESTDIR:-} ]] || systemctl --user daemon-reload 2>/dev/null || true
  echo "Removed $file"
  exit 0
fi
install -d -m755 "$dir"
cat >"$file" <<'CONF'
# MSeries: no portal without a display; see mseries/install-portal-relogin-fix.sh
[Unit]
ConditionEnvironment=WAYLAND_DISPLAY
CONF
chmod 644 "$file"
[[ -n ${DESTDIR:-} ]] || systemctl --user daemon-reload
echo "Installed $file (takes effect the next time the portal starts; the running portal is untouched)"
