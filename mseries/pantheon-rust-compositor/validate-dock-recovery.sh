#!/usr/bin/env bash
# validate-dock-recovery.sh — read-only check that the RUNNING Rust compositor is the
# installed one and that external monitors are published with a real identity, once
# per monitor, with a good link.
#
#   bash mseries/pantheon-rust-compositor/validate-dock-recovery.sh [REPORT_FILE]
#
# Writes the report to REPORT_FILE (default ~/.local/state/mseries/dock-recovery-*.txt)
# and exits 0 only when every check passes. Changes nothing. Run it after logging in
# with the dock attached. Background: mseries/aurora/hardware-tests/2026-10-21-j314s-dock-replug-stale-connector.md
set -u

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
report=${1:-$HOME/.local/state/mseries/dock-recovery-$(date +%Y%m%d-%H%M%S).txt}
mkdir -p "$(dirname "$report")"
: >"$report"
failed=0
unit=pantheon-rust-compositor@wayland.service

say() { printf '%s\n' "$*" | tee -a "$report"; }
ok() { say "  PASS  $*"; }
bad() { say "  FAIL  $*"; failed=1; }

say "dock recovery validation $(date -Is) on $(uname -r)"

# 1. The compositor is up (a fresh login can take a while).
for _ in $(seq 1 60); do
  systemctl --user is-active --quiet "$unit" && break
  sleep 2
done
if systemctl --user is-active --quiet "$unit"; then ok "$unit is active"; else bad "$unit is not active"; fi
sleep 5 # let the udev reconcile and its follow-up run

# 2. The running executable is the installed one, not a replaced-on-disk leftover.
pid=$(systemctl --user show -p MainPID --value "$unit" 2>/dev/null)
say "package: $(dpkg-query -W -f='${Version}' pantheon-rust-compositor 2>/dev/null)"
if [ -n "$pid" ] && [ "$pid" != 0 ] && [ -r "/proc/$pid/exe" ]; then
  running=$(sha256sum "/proc/$pid/exe" | cut -c1-16)
  installed=$(sha256sum /usr/bin/pantheon-compositor | cut -c1-16)
  if [ "$running" = "$installed" ]; then
    ok "running binary matches /usr/bin/pantheon-compositor ($installed)"
  else
    bad "running binary $running differs from installed $installed (login again to load the new one)"
  fi
else
  bad "cannot inspect the compositor process (pid '${pid:-none}')"
fi

# 3. Published monitors: real identity, one entry per monitor.
state=$(python3 -I - <<'PY' 2>&1
from gi.repository import Gio
b = Gio.bus_get_sync(Gio.BusType.SESSION, None)
r = b.call_sync("org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
                "org.gnome.Mutter.DisplayConfig", "GetCurrentState", None, None,
                Gio.DBusCallFlags.NONE, 5000, None).unpack()
for spec, modes, _props in r[1]:
    cur = next((m[0] for m in modes if m[6].get("is-current")), "-")
    print("|".join([spec[0], spec[1], spec[2], spec[3], cur]))
PY
)
if [ $? -ne 0 ] || [ -z "$state" ]; then
  bad "could not read org.gnome.Mutter.DisplayConfig: ${state:-no output}"
else
  say "published monitors (connector|vendor|product|serial|mode):"
  printf '%s\n' "$state" | sed 's/^/    /' | tee -a "$report"
  externals=$(printf '%s\n' "$state" | grep -v '^eDP' || true)
  if [ -z "$externals" ]; then
    say "  NOTE  no external monitor is published (dock not attached, or not recovered)"
    bad "no external monitor published"
  else
    if printf '%s\n' "$externals" | cut -d'|' -f2 | grep -qx Apple; then
      bad "an external monitor is still published as vendor Apple (no EDID identity)"
    else
      ok "external monitors carry their EDID identity"
    fi
    dup=$(printf '%s\n' "$externals" | cut -d'|' -f2-4 | sort | uniq -d)
    if [ -n "$dup" ]; then bad "the same monitor is published more than once: $dup"; else ok "each external monitor appears once (no phantom)"; fi
  fi
fi

# 4. Links of the published connectors are good.
health=$(bash "$here/../check-display-paths.sh" 2>/dev/null | sed -n '/Connector health/,/Verdict/p')
published=$(printf '%s\n' "${state:-}" | cut -d'|' -f1)
for connector in $published; do
  line=$(printf '%s\n' "$health" | grep -E "card[0-9]+-${connector} link-status" | head -1)
  case "$line" in
    *Good*) ok "$connector link-status Good" ;;
    *Bad*) bad "$connector link-status is still Bad" ;;
    *) say "  NOTE  $connector link-status not reported" ;;
  esac
done

# 5. Evidence from the compositor journal (informational).
say "compositor journal since this login:"
journalctl --user -b --no-pager -o short-monotonic -u "$unit" 2>/dev/null \
  | grep -E 'link-status was Bad|could not reset link-status|ignoring connector|mapped newly connected|unmapped disconnected|native output render failed' \
  | sed 's/^/    /' | tail -20 | tee -a "$report"

say "report: $report"
if [ "$failed" = 0 ]; then say "RESULT: PASS"; else say "RESULT: FAIL"; fi
exit "$failed"
