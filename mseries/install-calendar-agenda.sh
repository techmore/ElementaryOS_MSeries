#!/usr/bin/env bash
# Build a pinned Pantheon agenda with separate Events/Tasks and online accounts.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin="$(pkg-config --variable=indicatorsdir wingpanel-9)/libdatetime.so"
source "$repo/mseries/lib-backup.sh"
if [[ ${1:-} == --uninstall ]]; then
    mseries_restore "$plugin" io.elementary.panel.datetime
    sudo rm -f /usr/local/bin/mseries-calendar-accounts
    exit
fi
version=$(dpkg-query -W -f='${Version}' io.elementary.panel.datetime)
[[ ${version#*:} =~ ^2\.4\.2([+~.-]|$) ]] || { echo "Agenda targets datetime 2.4.2, found $version" >&2; exit 1; }
work=$(mktemp -d "${TMPDIR:-/tmp}/mseries-calendar.XXXXXX")
trap 'rm -rf "$work"' EXIT
readarray -t pin < <(python3 - "$repo/mseries/panel-factory-pins.json" <<'PY'
import json, sys
entry = next(p for p in json.load(open(sys.argv[1]))['indicators'] if p['name'] == 'datetime')
print(entry['repository']); print(entry['commit'])
PY
)
git init -q "$work/source"
git -C "$work/source" remote add origin "${pin[0]}"
git -C "$work/source" fetch -q --depth=1 origin "${pin[1]}"
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/datetime-agenda-tabs.patch"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir="$(dpkg-architecture -qDEB_HOST_MULTIARCH | sed 's|^|lib/|')" --buildtype=release
ninja -C "$work/build"
if ldd "$work/build/libdatetime.so" | grep -q 'not found'; then
    echo 'Missing runtime libraries; installed indicator preserved.' >&2
    exit 1
fi
mseries_backup "$plugin" io.elementary.panel.datetime
sudo install -Dm755 "$repo/mseries/calendar/accounts" /usr/local/bin/mseries-calendar-accounts
# Rename into place from a sibling directory: never truncate a library mapped by the running
# Wingpanel, and never leave a temp module inside the directory it watches.
mseries_install_indicator 644 "$work/build/libdatetime.so" "$plugin"
echo 'Installed Events/Tasks agenda. Reload Wingpanel to activate. Calendar Accounts opens Google sign-in.'
