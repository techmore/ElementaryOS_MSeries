#!/usr/bin/env bash
# Build the patched Pantheon Files .debs (libpantheon-files-core0 + pantheon-files, arm64).
#
#   OUTDIR=out/files-debs bash mseries/debs/build-files.sh
#
# Patch: mseries/patches/files-created-column-preview.patch (Created column, Date Created
# sort, default sort setting, preview pane beside the list view), applied to the pinned
# upstream commit that matches the packaged daily build (7.3.3+r6841, 2026-10-21).
# Version: 1:7.3.3+r6841+mseries<commit time>. The epoch beats any later Ubuntu/elementary
# daily (7.3.3+rNNNN+pkgNNN~daily), so `apt upgrade` keeps this build; the pin written by
# install-files-created-column.sh makes that explicit. Dependencies are copied from the
# installed package, so run this on the target machine (or one with the same archive).
set -euo pipefail

OUTDIR=${OUTDIR:?set OUTDIR to the output directory}
HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ROOT=$(cd -- "$HERE/../.." && pwd)
PATCH=$ROOT/mseries/patches/files-created-column-preview.patch
UPSTREAM_COMMIT=8f4915ea6a3eebc5c510b8e29bbdd6f7049ee009
BASE_VERSION=7.3.3+r6841

stamp=$(date -u -d "@$(git -C "$ROOT" show -s --format=%ct HEAD)" +%Y%m%d%H%M%S)
VERSION=1:$BASE_VERSION+mseries$stamp
mkdir -p "$OUTDIR"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/mseries-files-deb.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

git init -q "$WORK/src"
git -C "$WORK/src" fetch -q --depth 1 https://github.com/elementary/files.git "$UPSTREAM_COMMIT"
git -C "$WORK/src" checkout -q FETCH_HEAD
# The portal start-up fix (install-files-portal-fix.sh) is not needed here: this upstream
# commit no longer calls Granite.Settings in the portal constructor.
git -C "$WORK/src" apply "$PATCH"

meson setup "$WORK/build" "$WORK/src" --prefix=/usr --libexecdir=lib/aarch64-linux-gnu -Dwith-zeitgeist=disabled >/dev/null
nice -n 10 ninja -C "$WORK/build"
DESTDIR=$WORK/dest meson install -C "$WORK/build" --no-rebuild >/dev/null

# Split: the shared library goes to its own package, as in the archive.
libdir=usr/lib/aarch64-linux-gnu
mkdir -p "$WORK/core/$libdir" "$WORK/files"
cp -a "$WORK"/dest/$libdir/libpantheon-files-core.so.7 "$WORK"/dest/$libdir/libpantheon-files-core.so.7.3.3 "$WORK/core/$libdir/"
rm -f "$WORK"/dest/$libdir/libpantheon-files-core.so* "$WORK"/dest/$libdir/pkgconfig/pantheon-files-core.pc
rm -rf "$WORK/dest/usr/include"
rmdir "$WORK/dest/$libdir/pkgconfig" 2>/dev/null || true
cp -a "$WORK/dest/." "$WORK/files/"

dep() { dpkg-query -W -f="\${$1}" "$2"; }
files_depends=$(dep Depends pantheon-files | sed -E "s/libpantheon-files-core0 \(= [^)]*\)/libpantheon-files-core0 (= $VERSION)/")
core_depends=$(dep Depends libpantheon-files-core0)

control() { # PKG SECTION DEPENDS [RECOMMENDS]
  mkdir -p "$WORK/$1/DEBIAN"
  {
    echo "Package: $2"; echo "Version: $VERSION"; echo "Architecture: arm64"
    echo "Maintainer: M-series <noreply@techmore.dev>"; echo "Section: $3"; echo "Priority: optional"
    echo "Depends: $4"
    [[ -z ${5:-} ]] || echo "Recommends: $5"
    echo "Description: $6"
  } > "$WORK/$1/DEBIAN/control"
}
control core libpantheon-files-core0 libs "$core_depends" "" "Pantheon Files core library (M-series build)
 Adds the Created column and sort used by the patched Files."
control files pantheon-files x11 "$files_depends" "$(dep Recommends pantheon-files)" "Pantheon Files (M-series build)
 Created column, Date Created sort, default sort setting and a preview pane beside the list view."

for pkg in core:libpantheon-files-core0 files:pantheon-files; do
  dir=${pkg%%:*} name=${pkg##*:}
  dpkg-deb --root-owner-group -Zgzip -b "$WORK/$dir" "$OUTDIR/${name}_${VERSION//:/%3a}_arm64.deb" >/dev/null
done
echo "$VERSION" > "$OUTDIR/VERSION"
ls -1 "$OUTDIR"
