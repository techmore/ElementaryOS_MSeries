#!/usr/bin/env bash
# Screenshots of the elementary-styled lock screen (pantheon-lock + gtklock).
#
#   bash shoot.sh BIN OUTDIR [light|dark]
#
# Runs pantheon-compositor nested in a private Xvfb + D-Bus session, locks it
# through org.gnome.ScreenSaver.Lock with the repository's pantheon-lock, and
# saves 1-locked, 2-revealed, 3-typing (seven characters, never submitted, so
# no PAM attempt is made) and 4-capslock. Reads the user's real wallpaper and
# appearance settings read-only; `dark` uses a temporary keyfile backend.
# Set LOCK_WAYLAND_DEBUG=1 to keep gtklock's protocol log in OUTDIR/lock.err.
# Needs: xvfb-run, dbus-run-session, xdotool, gtklock, python3-pil.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BIN=$1 OUT=$2 SCHEME=${3:-light}
REPO=$(cd "$here/../../.." && pwd)
mkdir -p "$OUT"
export BIN REPO OUT SCHEME
xvfb-run -a -s "-screen 0 1280x800x24" dbus-run-session -- bash -c '
  rt=$(mktemp -d); chmod 700 "$rt"; export XDG_RUNTIME_DIR=$rt
  data=$REPO/mseries/pantheon-rust-compositor/session/usr/share/pantheon-rust-compositor/lock
  wrapper=$REPO/mseries/pantheon-rust-compositor/session/usr/bin/pantheon-lock
  printf "#!/bin/sh\nexport WAYLAND_DEBUG=${LOCK_WAYLAND_DEBUG:-0}\nexport PANTHEON_LOCK_DATA=%s\nexec %s 2>%s\n" "$data" "$wrapper" "$rt/lock.err" > "$rt/locker"; chmod +x "$rt/locker"
  if [ "$SCHEME" = dark ]; then
    export XDG_CONFIG_HOME=$rt/cfg GSETTINGS_BACKEND=keyfile; mkdir -p "$rt/cfg/glib-2.0/settings"
    wp=$(gsettings get org.gnome.desktop.background picture-uri)
    printf "[org/gnome/desktop/interface]\ncolor-scheme=\x27prefer-dark\x27\ngtk-theme=\x27io.elementary.stylesheet.blueberry\x27\nclock-format=\x2724h\x27\n[org/gnome/desktop/background]\npicture-uri-dark=%s\n" "$wp" > "$rt/cfg/glib-2.0/settings/keyfile"
  fi
  env -u WAYLAND_DISPLAY RUST_LOG=${COMP_LOG:-info} PANTHEON_LOCK_COMMAND="$rt/locker" "$BIN" --backend nested >"$rt/comp.log" 2>&1 &
  comp=$!
  for _ in $(seq 1 60); do ls "$rt" | grep -q "^wayland-[0-9]*$" && break; sleep 0.25; done
  for _ in $(seq 1 40); do gdbus call --session -d org.gnome.ScreenSaver -o /org/gnome/ScreenSaver -m org.gnome.ScreenSaver.GetActive >/dev/null 2>&1 && break; sleep 0.25; done
  for w in $(xdotool search --pid $comp 2>/dev/null); do xdotool windowfocus $w 2>/dev/null; done
  xdotool mousemove 640 400
  gdbus call --session -d org.gnome.ScreenSaver -o /org/gnome/ScreenSaver -m org.gnome.ScreenSaver.Lock >/dev/null
  sleep 3
  python3 -I -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay=\"$DISPLAY\").save(\"$OUT/1-locked.png\")"
  xdotool mousemove 660 420; xdotool key shift; sleep 1
  python3 -I -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay=\"$DISPLAY\").save(\"$OUT/2-revealed.png\")"
  xdotool mousemove 610 524 click 1; sleep 0.5; xdotool type --delay 80 "abcdefg"; sleep 1.5
  python3 -I -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay=\"$DISPLAY\").save(\"$OUT/3-typing.png\")"
  xdotool key Caps_Lock; sleep 1
  python3 -I -c "from PIL import ImageGrab; ImageGrab.grab(xdisplay=\"$DISPLAY\").save(\"$OUT/4-capslock.png\")"
  xdotool key Caps_Lock
  echo "--- compositor log"; grep -iE "focus|enter|lock surface|keyboard" "$rt/comp.log" | grep -vE "EGL|add_keyboard" | tail -25 | cut -c1-230
  echo "--- locker stderr"; grep -v "^$" "$rt/lock.err" | grep -vE "wl_callback|wl_surface|wl_buffer|wl_shm|wl_region|zwp_linux|wp_viewport|wl_display" | grep -iE "keyboard|wl_seat|error|warn|bus" | head -30
  kill $comp 2>/dev/null; wait $comp 2>/dev/null; cp "$rt/comp.log" "$OUT/comp.log"; cp "$rt/lock.err" "$OUT/lock.err" 2>/dev/null; rm -rf "$rt"'
