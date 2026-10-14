#!/usr/bin/env bash
# Install into a temporary root, check the drop-in, then uninstall cleanly.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(mktemp -d); trap 'rm -rf "$root"' EXIT
DESTDIR=$root bash "$here/install-greeter-obex-fix.sh" >/dev/null
conf=$root/etc/systemd/user/obex.service.d/10-mseries-greeter.conf
grep -qx '\[Service\]' "$conf" && grep -qx 'TimeoutStopSec=2s' "$conf" || { echo "FAIL drop-in content" >&2; exit 1; }
[[ $(stat -c %a "$conf") == 644 ]] || { echo "FAIL mode" >&2; exit 1; }
DESTDIR=$root bash "$here/install-greeter-obex-fix.sh" >/dev/null   # idempotent
DESTDIR=$root bash "$here/install-greeter-obex-fix.sh" --uninstall >/dev/null
[[ ! -e $conf && ! -d $root/etc/systemd/user/obex.service.d ]] || { echo "FAIL uninstall" >&2; exit 1; }
echo "greeter obex fix: ok"
