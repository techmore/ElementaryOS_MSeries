#!/usr/bin/env bash
# Private libmutter with the upstream fix for the Gala crash of 2026-10-18 (mseries/PANTHEON-CRASH-2026-10-18.md).
#
# Ubuntu's mutter 50.1 dereferences a destroyed Wayland surface in
# meta_surface_actor_wayland_get_cursor_for_sprite when a popup closes under the pointer, which kills
# Gala and the whole Pantheon session. Upstream fixed it in mutter c18af474 (51.alpha). This script
# rebuilds Ubuntu's exact mutter source and build flags plus that one patch, and installs only
# libmutter-18.so.0 into /usr/local/lib/mseries/gala/mutter-fix. The system mutter, GNOME Shell and
# the greeter are untouched; the mseries-gala launcher (install-gala-screen-corners.sh) puts the
# library on the patched Gala's path only while the system libmutter-18-0 version equals the one
# it was built from, so an Ubuntu mutter update simply turns it off.
#
#   bash mseries/install-gala-mutter-fix.sh              # build and install (sudo for the install step)
#   bash mseries/install-gala-mutter-fix.sh --uninstall  # remove
# Takes effect at the next Pantheon login.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dest=/usr/local/lib/mseries/gala/mutter-fix
patch_file=$repo/mseries/patches/mutter-surface-actor-null-cursor.patch

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -rf "$dest"
  echo "Removed $dest (stock libmutter at next login)"
  exit 0
fi

version=$(dpkg-query -W -f='${Version}' libmutter-18-0)
upstream=${version%-*}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

for tool in dpkg-source meson ninja patch curl; do
  command -v "$tool" >/dev/null || { echo "Missing $tool" >&2; exit 1; }
done
# Packages Ubuntu's mutter build needs beyond the Gala build requirements (tests and docs disabled).
need=(patchelf libei-dev libsysprof-6-dev sysprof libcanberra-gtk3-dev libpam0g-dev libumockdev-dev python3-argcomplete python3-docutils)
missing=()
for p in "${need[@]}"; do dpkg-query -W -f='${Status}' "$p" 2>/dev/null | grep -q 'install ok installed' || missing+=("$p"); done
if ((${#missing[@]})); then
  echo "Installing build requirements: ${missing[*]}"
  sudo apt-get install -y --no-install-recommends "${missing[@]}"
fi

# Source package for exactly the installed version; dpkg-source checks the .dsc checksums.
base=https://launchpad.net/ubuntu/+archive/primary/+sourcefiles/mutter/$version
cd "$work"
curl -fsSLO "$base/mutter_$version.dsc"
for f in $(awk '/^Checksums-Sha256/{f=1;next} /^[A-Z]/{f=0} f{print $3}' "mutter_$version.dsc"); do
  curl -fsSLO "$base/$f"
done
dpkg-source -x "mutter_$version.dsc" src >/dev/null
patch -d src -p1 --forward < "$patch_file"

# Same flags as debian/rules (tests and docs only affect other targets).
meson setup build src --prefix=/usr --libdir="lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)" --buildtype=plain \
  -Dc_args="$(dpkg-buildflags --get CFLAGS) $(dpkg-buildflags --get CPPFLAGS)" \
  -Dc_link_args="$(dpkg-buildflags --get LDFLAGS) -Wl,-O1" \
  -Dauto_features=enabled -Degl_device=true -Dremote_desktop=true -Dwayland_eglstream=true \
  -Dtests=disabled -Dclutter_tests=false -Dcogl_tests=false -Dmutter_tests=false -Ddocs=false >/dev/null
nice -n 19 ninja -C build -j"$(( $(nproc) > 2 ? $(nproc) - 2 : 1 ))" src/libmutter-18.so.0.0.0 >/dev/null
lib=build/src/libmutter-18.so.0.0.0
# Must keep the system private-library path, like the packaged library.
patchelf --force-rpath --set-rpath "/usr/lib/$(dpkg-architecture -qDEB_HOST_MULTIARCH)/mutter-18" "$lib"

sudo install -d -m755 "$dest"
sudo install -m644 "$lib" "$dest/libmutter-18.so.0"
echo "$version" | sudo tee "$dest/mutter-version" >/dev/null
echo "Installed $dest/libmutter-18.so.0 for mutter $version ($upstream + c18af474). Takes effect at the next Pantheon login."
