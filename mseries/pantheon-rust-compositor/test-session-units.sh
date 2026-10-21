#!/bin/sh
# Static checks for the experimental Rust session units. Headless; touches no
# running session. Run from anywhere: sh test-session-units.sh
set -eu
d=$(cd "$(dirname "$0")" && pwd)/session/usr/lib/systemd/user
fail=0
check() { if ! grep -q -- "$2" "$d/$1"; then echo "FAIL $1: missing '$2'" >&2; fail=1; fi; }
for u in pantheon-wingpanel.service pantheon-dock.service; do
    check $u 'GSK_RENDERER=gl'
    check $u 'BindsTo=pantheon-rust-compositor@wayland.service'
    check $u 'After=pantheon-rust-compositor@wayland.service'
    check $u 'Restart=on-failure'
done
check pantheon-dock.service 'pantheon-wingpanel.service'
check pantheon-dock.service 'user-disabled'
check 'pantheon-rust-compositor@.service' 'Type=notify'
check 'pantheon-rust-compositor@.service' 'dbus-update-activation-environment --systemd WAYLAND_DISPLAY'
check 'gnome-session@pantheon-rust-wayland.target.d/session.conf' 'Wants=pantheon-wingpanel.service'
check 'gnome-session@pantheon-rust-wayland.target.d/session.conf' 'Wants=pantheon-dock.service'
check pantheon-dock.service 'CPUWeight=400'
check session.slice.d/50-mseries-latency.conf 'CPUWeight=500'
check user.slice.d/50-mseries-batch.conf 'CPUWeight=20'
if command -v systemd-analyze >/dev/null 2>&1; then
    systemd-analyze --user verify "$d"/pantheon-wingpanel.service "$d"/pantheon-dock.service 2>&1 \
        | grep -v -E 'Failed to (prepare|load)|not found|Command .* is not executable|No such file' || true
fi
[ $fail -eq 0 ] && echo "session unit checks passed"
exit $fail
