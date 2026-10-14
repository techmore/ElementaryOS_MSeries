#!/usr/bin/env bash
# Stop the LightDM greeter's user manager (user@<lightdm uid>) from failing at every login.
#
# The greeter's panel (io.elementary.wingpanel -g) D-Bus-activates the Bluetooth OBEX daemon. At logout
# obexd hangs, waiting on Evolution data-server activation it asked for, so it ignores SIGTERM until the
# 5 s user@ stop timeout kills it and marks user@109.service failed (journal 2026-10-14 15:47 and 16:33).
# A short stop timeout on obex.service lets systemd kill just obexd first, so the user manager stops
# cleanly. Behaviour is unchanged otherwise; an OBEX transfer in flight at logout is cut after 2 s.
#
#   sudo bash mseries/install-greeter-obex-fix.sh              # install
#   sudo bash mseries/install-greeter-obex-fix.sh --uninstall  # remove
# DESTDIR=/some/root is honoured for testing.
set -euo pipefail
dir="${DESTDIR:-}/etc/systemd/user/obex.service.d"
file="$dir/10-mseries-greeter.conf"
if [[ ${1:-} == --uninstall ]]; then
  rm -f "$file"
  rmdir "$dir" 2>/dev/null || true
  [[ -n ${DESTDIR:-} ]] || systemctl --global daemon-reload 2>/dev/null || true
  echo "Removed $file"
  exit 0
fi
install -d -m755 "$dir"
cat >"$file" <<'CONF'
# MSeries: obexd hangs at logout in the LightDM greeter; see mseries/install-greeter-obex-fix.sh
[Service]
TimeoutStopSec=2s
CONF
chmod 644 "$file"
echo "Installed $file (takes effect for the next greeter session; no restart needed)"
