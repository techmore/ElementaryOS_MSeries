#!/usr/bin/env bash
# Read-only check of the M-series "drawers" stack: the Gala plugin, the patched
# dock, the hotkeys and the config. Changes nothing.
#
#   bash mseries/check-drawers.sh
#
# Run it before a reboot (shows what is installed) and again after logging back
# in (shows what is actually live in the session). The plugin and the dock only
# load at Gala/dock start, so "installed" and "live" are different questions.

ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; }
bad()  { printf '  \033[31m✗\033[0m %s\n' "$1"; }
warn() { printf '  \033[33m!\033[0m %s\n' "$1"; }
head1() { printf '\n\033[1m%s\033[0m\n' "$1"; }

head1 "Patched Gala (compositor)"
launcher=/usr/local/lib/mseries/gala/bin/mseries-gala
dropin=$HOME/.config/systemd/user/io.elementary.gala@wayland.service.d/mseries-screen-corners.conf
[ -x "$launcher" ] && ok "launcher present: $launcher" || bad "launcher missing: $launcher"
if [ -f "$dropin" ]; then
    ok "session drop-in installed (patched Gala is used at next login)"
else
    warn "no session drop-in — the stock Gala runs (revert state)"
fi
grep -q set_offset /usr/local/lib/mseries/gala/bin/gala 2>/dev/null \
    && ok "panel-offset protocol present in the installed Gala (v2)" \
    || warn "installed Gala has no set_offset — Command-drag will stay centred"

head1 "Drawers plugin (Gala)"
plugin=/usr/local/lib/mseries/gala/lib/gala/plugins/libgala-drawers.so
[ -f "$plugin" ] && ok "plugin installed: $plugin" || bad "plugin not installed"
gala_pid=$(pgrep -x gala | head -1)
if [ -n "$gala_pid" ]; then
    echo "  running gala pid $gala_pid ($(readlink -f /proc/$gala_pid/exe 2>/dev/null))"
    if grep -q libgala-drawers "/proc/$gala_pid/maps" 2>/dev/null; then
        ok "plugin is LOADED in the running session"
    else
        warn "plugin installed but not loaded — needs a logout/login"
    fi
else
    warn "no running gala found"
fi

head1 "Hotkeys (gsettings)"
schema=org.pantheon.gala.plugins.drawers
if gsettings writable "$schema" drawer-1 >/dev/null 2>&1; then
    for n in 1 2; do
        printf '  drawer-%s = %-28s assign-%s = %s\n' "$n" \
            "$(gsettings get "$schema" "drawer-$n" 2>/dev/null)" "$n" \
            "$(gsettings get "$schema" "assign-$n" 2>/dev/null)"
    done
    ok "schema readable (left Command = Control here: Control+N toggles, Control+Alt+N assigns)"
else
    warn "schema $schema not visible to gsettings (install it per-user)"
fi

head1 "Patched dock"
dock_pid=""
for p in $(pgrep -f '[i]o.elementary.dock'); do
    case "$(readlink -f "/proc/$p/exe" 2>/dev/null)" in
        */io.elementary.dock) dock_pid=$p; break ;;
    esac
done
wrapper=$HOME/.local/bin/io.elementary.dock
patched=$HOME/.local/lib/mseries/dock/bin/io.elementary.dock
[ -x "$patched" ] && ok "private build present: $patched" || warn "no private dock build"
if [ -x "$wrapper" ]; then
    ok "session wrapper present: $wrapper"
else
    warn "no wrapper — the stock dock runs"
fi
if [ -n "$dock_pid" ]; then
    exe=$(readlink -f "/proc/$dock_pid/exe" 2>/dev/null)
    echo "  running dock pid $dock_pid -> $exe"
    case "$exe" in
        "$patched")  ok "the PATCHED dock is running (chevron + Command-drag active)" ;;
        /usr/bin/*)  warn "the STOCK dock is running — wrapper not picked up yet" ;;
        *)           warn "unexpected dock binary: $exe" ;;
    esac
else
    warn "no running dock found"
fi
ldd "$patched" 2>/dev/null | grep -q 'not found' && bad "private dock build has unresolved libraries" || true

head1 "Drawer config"
cfg=$HOME/.config/mseries/gala-drawers.ini
if [ -f "$cfg" ]; then
    ok "config present: $cfg"
    grep -c '^\[drawer-' "$cfg" | xargs -I{} echo "  {} drawer slot(s) configured"
    sed -n '1,12p' "$cfg" | sed 's/^/    /'
else
    warn "no config yet — assign one with Control+Alt+1..9 or the settings app"
fi
settings=$HOME/.local/bin/mseries-drawers-settings
[ -x "$settings" ] && ok "settings app installed: $settings" || warn "settings app not installed"

head1 "Verdict"
echo "  Nothing above changes anything. Revert: install-dock-drawers.sh --revert,"
echo "  install-gala-screen-corners.sh --disable (both take effect at next login)."
