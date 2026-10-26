#!/usr/bin/env bash
# Exercise linked production widgets with fake collectors and private desktop state.
set -euo pipefail
source_dir=${1:?usage: test-unified.sh PREPARED_SOURCE BUILD OUTPUT}
build_dir=${2:?}
out=$(realpath -m "${3:?}")
mkdir -p "$out"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/home/.local/bin" "$work/runtime"
chmod 700 "$work/runtime"
cat > "$work/bus.conf" <<'BUS'
<busconfig><type>session</type><listen>unix:tmpdir=/tmp</listen><policy context="default"><allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/></policy></busconfig>
BUS
cat > "$work/home/.local/bin/codexbar-linux" <<'BACKEND'
#!/bin/sh
[ "$1" = --snapshot ] && echo snapshot >> "$HOME/snapshot-calls"
[ "$1" = --snapshot ] && printf '{"entries":[]}'
exit 0
BACKEND
cat > "$work/home/.local/bin/mseries-repobar" <<'BACKEND'
#!/bin/sh
touch "$HOME/helper-called"
printf '{"account":"fixture","host":"github.com","fetchedAt":1793016000,"repos":[],"settings":{"showContributions":false}}'
BACKEND
cat > "$work/home/.local/bin/t3-fixture" <<'BACKEND'
#!/bin/sh
printf '%s\n' "$@" >> "$HOME/action-calls"
BACKEND
mkdir -p "$work/home/.local/share/applications"
cat > "$work/home/.local/share/applications/io.github.techmore.ClaudePantheonRs.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=T3 fixture
Exec=$work/home/.local/bin/t3-fixture --full
Actions=activity;open-full;
[Desktop Action activity]
Name=Activity
Exec=$work/home/.local/bin/t3-fixture --activity
[Desktop Action open-full]
Name=Open T3
Exec=$work/home/.local/bin/t3-fixture --full
DESKTOP
chmod +x "$work/home/.local/bin/"*
glib-compile-schemas "$source_dir/data"
cat > "$work/run.sh" <<'RUN'
#!/usr/bin/env bash
set -euo pipefail
export DBUS_SYSTEM_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS"
rm -f "$HOME/helper-called" "$HOME/snapshot-calls" "$HOME/action-calls"
"$TEST_BINARY" > "$TEST_OUTPUT/fixture-$TEST_DARK.log" 2>&1 &
fixture_pid=$!
trap 'kill "$fixture_pid" 2>/dev/null || true' EXIT
sleep 4
ffmpeg -loglevel error -f x11grab -video_size 1100x1000 -i "$DISPLAY" -frames:v 1 -update 1 -y "$TEST_OUTPUT/usage-$TEST_DARK.png"
sleep 1.5
ffmpeg -loglevel error -f x11grab -video_size 1100x1000 -i "$DISPLAY" -frames:v 1 -update 1 -y "$TEST_OUTPUT/github-$TEST_DARK.png"
wait "$fixture_pid"
RUN
for dark in 0 1; do
  env HOME="$work/home" XDG_CONFIG_HOME="$work/home/.config" XDG_CACHE_HOME="$work/home/.cache" \
    XDG_DATA_HOME="$work/home/.local/share" XDG_RUNTIME_DIR="$work/runtime" \
    GSETTINGS_BACKEND=memory GSETTINGS_SCHEMA_DIR="$source_dir/data" GIO_USE_VFS=local \
    GDK_BACKEND=x11 GSK_RENDERER=cairo GTK_A11Y=none G_DEBUG=fatal-criticals \
    TEST_BINARY="$build_dir/src/test-unified" TEST_OUTPUT="$out" TEST_DARK="$dark" \
    xvfb-run -a -s '-screen 0 1100x1000x24' dbus-run-session --config-file="$work/bus.conf" -- bash "$work/run.sh"
  cat "$out/fixture-$dark.log"
done
