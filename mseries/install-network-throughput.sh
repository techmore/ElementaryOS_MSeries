#!/usr/bin/env bash
# Add live download/upload speed and a 60 s graph to the Wingpanel network indicator's dropdown.
# Builds io.elementary.panel.network (elementary/panel-network) with
# mseries/patches/network-throughput.patch and replaces only libnetwork.so.
#
#   bash mseries/install-network-throughput.sh              # build + install + reload the panel
#   bash mseries/install-network-throughput.sh --uninstall  # restore the original plugin
#
# A package upgrade of io.elementary.panel.network overwrites the plugin; just re-run this script.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin=/usr/lib/aarch64-linux-gnu/wingpanel-9/libnetwork.so
source "$repo/mseries/lib-backup.sh"
commit=8685ec8e55a45e48da0c12931a353cd440d11664   # matches io.elementary.panel.network 8.0.1+r1290

reload_panel() {
  # Gala starts Wingpanel as a shell client and respawns it, so this loads the new plugin
  # without logging out. Harmless if the panel is not running.
  pkill -x io.elementary.w 2>/dev/null || true
}

if [[ ${1:-} == --uninstall ]]; then
  mseries_restore "$plugin" io.elementary.panel.network
  reload_panel
  echo 'Restored the original network indicator.'
  exit 0
fi

for tool in git meson ninja valac msgfmt pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install the build requirements with:" >&2
    echo '  sudo apt install git meson ninja-build valac gettext libwingpanel-9-dev libgranite-7-dev libgtk-4-dev libnm-dev libnma-gtk4-dev libpolkit-gobject-1-dev libsqlite3-dev' >&2
    exit 1
  }
done
for mod in wingpanel-9 granite-7 gtk4 libnm libnma-gtk4 polkit-gobject-1 sqlite3; do
  pkg-config --exists "$mod" || { echo "Missing development files for $mod (see apt line above)." >&2; exit 1; }
done

installed_version=$(dpkg-query -W -f='${Version}' io.elementary.panel.network 2>/dev/null || true)
if [[ $installed_version != 8.0.1* ]]; then
  echo "This patch targets io.elementary.panel.network 8.0.1.x; found ${installed_version:-none}." >&2
  exit 1
fi

work_dir=$(mktemp -d "${TMPDIR:-/tmp}/network-throughput.XXXXXX")
trap 'rm -rf "$work_dir"' EXIT
source_dir="$work_dir/source"
build_dir="$work_dir/build"

git init -q "$source_dir"
git -C "$source_dir" remote add origin https://github.com/elementary/panel-network.git
git -C "$source_dir" fetch -q --depth=1 origin "$commit"
git -C "$source_dir" checkout -q --detach FETCH_HEAD
git -C "$source_dir" apply "$repo/mseries/patches/network-throughput.patch"
git -C "$source_dir" apply "$repo/mseries/patches/network-null-devices.patch"
git -C "$source_dir" apply "$repo/mseries/patches/network-panel-speed.patch"
git -C "$source_dir" apply \
  --include=data/Indicator.css \
  --include=src/Widgets/UsageWidget.vala \
  --include=src/Widgets/WifiInterface.vala \
  "$repo/mseries/netspeed/panel-network.patch"
python3 "$repo/mseries/netspeed/wire-network-usage.py" "$source_dir"

meson setup "$build_dir" "$source_dir" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release >/dev/null
ninja -C "$build_dir" >/dev/null
built="$build_dir/libnetwork.so"
test -f "$built"
if ldd "$built" | grep -q 'not found'; then
  echo 'The built plugin has unresolved libraries; leaving the installed one unchanged.' >&2
  exit 1
fi

mseries_backup "$plugin" io.elementary.panel.network
sudo install -m 0644 "$built" "$plugin"
reload_panel
echo 'Installed. The network menu has the speed graph, collapsible Wi-Fi networks, and Network Usage. Run mseries/netspeed/netusage/install.sh to populate Apps/Hosts/DNS.'
