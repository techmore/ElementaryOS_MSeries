#!/bin/bash
# Headless test of the Quick Settings AirDrop section against the stub backend (mseries/omdrop-stub). Nothing appears on any screen.
# Usage: run-probe.sh OUT_DIR
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd); repo=$(cd "$here/../../.." && pwd); out=$(realpath -m "$1"); mkdir -p "$out"
b=$(mktemp -d); trap 'rm -rf "$b"' EXIT
# Vala wants the sources inside the project directory, so build from a copy that includes the real panel source.
mkdir -p "$b/src" && cp "$here/meson.build" "$here/airdrop-probe.vala" "$repo/mseries/quick-settings/AirDropPanel.vala" "$b/src/"
meson setup "$b/build" "$b/src" --buildtype=debug >/dev/null && ninja -C "$b/build" >/dev/null
home=$(mktemp -d); mkdir -p "$home/share/icons/hicolor/scalable/apps"; cp "$repo/mseries/quick-settings/airdrop.svg" "$home/share/icons/hicolor/scalable/apps/mseries-airdrop-symbolic.svg"
probe() { # scenario, stub dir
  env -i PATH="$PATH" HOME="$home" OMDROP_CLI="$repo/mseries/omdrop-stub/omdrop" OMDROP_STUB_DIR="$2" PROBE_SCENARIO="$1" XDG_DATA_DIRS="$home/share:/usr/share" LANG=C.UTF-8 \
    GTK_THEME=io.elementary.stylesheet.blueberry GSK_RENDERER=cairo GDK_BACKEND=x11 xvfb-run -a -s "-screen 0 500x600x24" "$b/build/airdrop-probe" "$out/$1"
}
fail=0; check() { if grep -q -- "$2" <<<"$1"; then echo "ok   $3"; else echo "FAIL $3"; fail=1; fi; }
s1=$(mktemp -d); r=$(probe normal "$s1"); echo "$r"
check "$r" "collapsed-initial expanded=false status=Off" "starts collapsed and says Off"
check "$r" "^expanded status=Off" "opens when the row is clicked"
check "$r" "after-on switch=true status=Visible to everyone" "switch turns receiving on and the row says who can see it"
check "$r" "after-off switch=false status=Off" "switch turns receiving off"
check "$(cat "$s1/calls")" "on 10m" "ran: omdrop on 10m"
check "$(cat "$s1/calls")" "off" "ran: omdrop off"
s2=$(mktemp -d); touch "$s2/no-driver"; r=$(probe nodriver "$s2"); echo "$r"
check "$r" "status=Needs the Wi-Fi driver" "without the driver the row says so"
check "$r" "problem=Not ready: The Wi-Fi driver" "and explains why in plain words"
rm -rf "$home" "$s1" "$s2"
exit $fail
