#!/bin/bash
# Fix the ~25 second login stall caused by Pantheon Files' file chooser portal.
#
# At startup the Files portal calls Granite.Settings, which auto-starts
# org.freedesktop.portal.Desktop. That portal is itself waiting for the Files
# portal to claim its bus name, so both wait out the 25s D-Bus timeout. The
# patch waits for the main portal to be running before touching Granite.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
patch="$repo/mseries/patches/files-portal-startup-deadlock.patch"
bin=/usr/lib/aarch64-linux-gnu/io.elementary.files.xdg-desktop-portal
# Matches the packaged daily build (GTK 3); keep in step with the installed package.
commit=f966e0108
source "$repo/mseries/lib-backup.sh"

if [[ ${1:-} == --uninstall ]]; then
  mseries_restore "$bin" pantheon-files
  echo 'Restored the packaged Files portal.'
  exit 0
fi

# The patch is built from a pinned upstream commit that matches this packaged version.
version=$(dpkg-query -W -f='${Version}' pantheon-files 2>/dev/null || true)
[[ $version == 7.3.3* ]] || { echo "This patch targets pantheon-files 7.3.3.x; found ${version:-none}." >&2; exit 1; }

for tool in git meson ninja valac; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo '  sudo apt install git meson ninja-build valac libgtk-3-dev libgranite-dev libhandy-1-dev libportal-dev libportal-gtk3-dev libpoppler-glib-dev libcanberra-dev libsqlite3-dev libgee-0.8-dev libgit2-glib-1.0-dev libcloudproviders-dev libnotify-dev libwingpanel-9-dev' >&2
    exit 1
  }
done

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/files-portal-fix.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
git clone -q https://github.com/elementary/files.git "$build_dir/src"
git -C "$build_dir/src" checkout -q "$commit"
git -C "$build_dir/src" apply "$patch"
meson setup "$build_dir/build" "$build_dir/src" --prefix=/usr -Dwith-zeitgeist=disabled
ninja -C "$build_dir/build" filechooser-portal/io.elementary.files.xdg-desktop-portal

mseries_backup "$bin" pantheon-files
sudo install -m755 "$build_dir/build/filechooser-portal/io.elementary.files.xdg-desktop-portal" "$bin"
echo 'Installed the fixed Files portal. Log out and back in to load it.'
