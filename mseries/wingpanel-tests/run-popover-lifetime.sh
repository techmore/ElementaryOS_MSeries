#!/bin/bash
# Usage: run-popover-lifetime.sh [PINNED_SOURCE_DIR] [--unpatched]
# Builds the public pinned Wingpanel classes under Xvfb, never the user's panel.
set -euo pipefail
ulimit -c 0 # The negative control must not create another system coredump.
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
pin=6b8ae0453b1fd6dc07bd246642998011f04b2125
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
source_dir=${1:-}
if [[ -z $source_dir ]]; then
  source_dir="$work/upstream"
  git init -q "$source_dir"
  git -C "$source_dir" fetch -q --depth=1 https://github.com/elementary/wingpanel.git "$pin"
  git -C "$source_dir" checkout -q --detach FETCH_HEAD
fi
[[ $(git -C "$source_dir" rev-parse HEAD) == "$pin" ]]
mkdir -p "$work/src/Services" "$work/src/Widgets" "$work/home" "$work/runtime"
for path in src/Services/PopoverManager.vala src/Widgets/IndicatorEntry.vala; do
  git -C "$source_dir" show "$pin:$path" > "$work/$path"
done
if [[ ${2:-} != --unpatched ]]; then
  (cd "$work" && git apply "$repo/mseries/patches/wingpanel-popover-lifetime.patch")
fi
chmod 700 "$work/runtime"
# No service activation: a real document/settings portal must not mount inside the fixture.
cat > "$work/bus.conf" <<'XML'
<!DOCTYPE busconfig PUBLIC "-//freedesktop//DTD D-Bus Bus Configuration 1.0//EN"
 "http://www.freedesktop.org/standards/dbus/1.0/busconfig.dtd">
<busconfig>
  <type>session</type><listen>unix:tmpdir=/tmp</listen><auth>EXTERNAL</auth>
  <policy context="default">
    <allow send_destination="*"/><allow receive_sender="*"/><allow own="*"/>
  </policy>
</busconfig>
XML
valac --directory "$work" --pkg gtk4 --pkg granite-7 --pkg wingpanel-9 -o "$work/probe" \
  "$repo/mseries/wingpanel-tests/popover-lifetime.vala" \
  "$work/src/Services/PopoverManager.vala" "$work/src/Widgets/IndicatorEntry.vala" \
  >"$work/build.log" 2>&1 || { cat "$work/build.log"; exit 1; }
for action in switch close; do
  for animations in 0 1; do
    env -i HOME="$work/home" PATH="$PATH" LANG=C.UTF-8 \
      XDG_RUNTIME_DIR="$work/runtime" GTK_A11Y=none GSETTINGS_BACKEND=memory \
      GDK_BACKEND=x11 GSK_RENDERER=cairo TEST_ACTION="$action" TEST_ANIMATIONS="$animations" \
      timeout 30s xvfb-run -a dbus-run-session --config-file="$work/bus.conf" -- "$work/probe" >"$work/run.log" 2>&1 \
      || { cat "$work/run.log"; exit 1; }
    echo "PASS removed anchor: $action (animations=$animations)"
  done
done
