#!/usr/bin/env bash
# Build PipeWire's LV2 filter-graph plugin (libspa-filter-graph-plugin-lv2.so) from the same upstream version as
# Ubuntu's PipeWire, because Ubuntu does not ship it. asahi-audio's speaker chain needs it.
#   bash mseries/install-pipewire-lv2.sh              # build and install the plugin
#   bash mseries/install-pipewire-lv2.sh --uninstall  # remove it
# Re-run after a PipeWire upgrade that changes the upstream version (the script refuses a version mismatch).
set -euo pipefail
dest=/usr/lib/aarch64-linux-gnu/spa-0.2/filter-graph/libspa-filter-graph-plugin-lv2.so

if [[ ${1:-} == --uninstall ]]; then sudo rm -f "$dest"; echo Removed.; exit 0; fi

version=$(dpkg-query -W -f='${Version}' libpipewire-0.3-0t64 | sed -E 's/^([0-9]+(\.[0-9]+)*).*/\1/')
sudo apt-get install -y liblilv-dev lv2-dev meson ninja-build git >/dev/null
work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
git clone -q --depth=1 --branch "$version" https://gitlab.freedesktop.org/pipewire/pipewire.git "$work/pw"
meson setup "$work/pw/b" "$work/pw" -Dlv2=enabled -Dexamples=disabled -Dtests=disabled -Ddocs=disabled -Dman=disabled >/dev/null
ninja -C "$work/pw/b" spa/plugins/filter-graph/libspa-filter-graph-plugin-lv2.so >/dev/null
sudo install -m 0644 "$work/pw/b/spa/plugins/filter-graph/libspa-filter-graph-plugin-lv2.so" "$dest"
echo "Installed LV2 filter plugin for PipeWire $version at $dest"
