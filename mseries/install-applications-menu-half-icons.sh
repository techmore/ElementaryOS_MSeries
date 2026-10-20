#!/usr/bin/env bash
# Builds the elementary Applications menu (Slingshot) with icons at half size:
# grid 64->32 and a denser 7x4 page (was 5x3), list rows 32->16, search results 32->16
# (patches/applications-menu-half-icons.patch).
# Upstream has no setting for this. Reload Wingpanel to activate; --uninstall restores the package build.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
plugin="$(pkg-config --variable=indicatorsdir wingpanel-9)/libslingshot.so"
source "$repo/mseries/lib-backup.sh"
if [[ ${1:-} == --uninstall ]]; then
  mseries_restore "$plugin" io.elementary.applications-menu
  echo 'Original Applications menu restored. Reload Wingpanel to activate.'
  exit
fi
version=$(dpkg-query -W -f='${Version}' io.elementary.applications-menu)
[[ $version == 8.0.4* ]] || { echo "Patch targets Applications menu 8.0.4, found $version" >&2; exit 1; }
work=$(mktemp -d /tmp/mseries-applications-menu.XXXXXX)
trap 'rm -rf "$work"' EXIT
git init -q "$work/source"
git -C "$work/source" remote add origin https://github.com/elementary/applications-menu.git
git -C "$work/source" fetch -q --depth=1 origin 06d7170edab4d1f93ebd14173a0e2afea98e9339
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/applications-menu-half-icons.patch"
meson setup "$work/build" "$work/source" --prefix=/usr --libdir=lib/aarch64-linux-gnu --buildtype=release
ninja -C "$work/build"
built=$(find "$work/build" -name libslingshot.so | head -1)
[[ -n $built ]] || { echo 'libslingshot.so was not built' >&2; exit 1; }
if ldd "$built" | grep -q 'not found'; then
  echo 'Missing runtime libraries; installed Applications menu preserved.' >&2
  exit 1
fi
mseries_backup "$plugin" io.elementary.applications-menu
sudo install -m644 "$built" "$plugin"
echo 'Installed the half-size icon Applications menu. Reload Wingpanel to activate.'
