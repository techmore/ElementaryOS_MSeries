#!/usr/bin/env bash
# Native quarter snaps plus enforced OS half-snap defaults. No session restart.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source_dir=$repo/mseries/window-snapping
plugindir=/usr/local/lib/mseries/gala/lib/gala/plugins
vapidir=${1:-}
work_dir=$(mktemp -d)
trap 'rm -rf "$work_dir"' EXIT
if [[ ! -d $plugindir ]]; then
    plugindir=$(pkg-config --variable=libdir gala)/gala/plugins
fi
stock_plugindir=$(pkg-config --variable=libdir gala)/gala/plugins
plugindirs=("$plugindir")
if [[ $stock_plugindir != "$plugindir" ]]; then
    plugindirs+=("$stock_plugindir")
fi
[[ $(pkg-config --modversion libmutter-18) == 50.* ]] || {
    echo 'This plugin requires the M-series Gala 8.6.2 / Mutter 50 desktop.' >&2; exit 1;
}
if [[ -z $vapidir ]]; then
    git init -q "$work_dir/gala"
    git -C "$work_dir/gala" fetch -q --depth=1 https://github.com/elementary/gala.git \
        f0791434ac40a50f2aec64700a47b3bb04145752
    git -C "$work_dir/gala" checkout -q --detach FETCH_HEAD
    vapidir=$work_dir/gala/vapi
fi
meson setup "$work_dir/build" "$source_dir" --buildtype=release \
    -Dvapidir="$vapidir" -Dplugindir="$plugindir"
ninja -C "$work_dir/build"
# Install schema before plugin. Rename the library so an existing mapped copy
# is never truncated underneath a running compositor.
sudo install -m644 "$source_dir/org.techmore.mseries.snapping.gschema.xml" /usr/share/glib-2.0/schemas/
sudo glib-compile-schemas /usr/share/glib-2.0/schemas
for plugin_target in "${plugindirs[@]}"; do
    sudo install -Dm644 "$work_dir/build/libmseries-snapping.so" "$plugin_target/.libmseries-snapping.so.new"
    sudo mv "$plugin_target/.libmseries-snapping.so.new" "$plugin_target/libmseries-snapping.so"
done

# Preserve distribution profile entries and add the local system database.
sudo mkdir -p /etc/dconf/profile /etc/dconf/db/local.d/locks
if [[ ! -e /etc/dconf/profile/user ]]; then
    printf 'user-db:user\n' | sudo tee /etc/dconf/profile/user >/dev/null
fi
if ! grep -qxF system-db:local /etc/dconf/profile/user; then
    printf '\nsystem-db:local\n' | sudo tee -a /etc/dconf/profile/user >/dev/null
fi
sudo install -m644 "$source_dir/10-mseries-snapping" /etc/dconf/db/local.d/
sudo install -m644 "$source_dir/locks" /etc/dconf/db/local.d/locks/mseries-snapping
sudo dconf update
echo 'Half snaps are enforced. Quarter snaps load at next sign-in; open apps remain running.'
