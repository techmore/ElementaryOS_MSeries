#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
OUTDIR=${OUTDIR:?set OUTDIR to the directory for the generated .deb}
mkdir -p "$OUTDIR"
OUTDIR=$(cd -- "$OUTDIR" && pwd)
ARCH=$(dpkg --print-architecture)
if [[ $ARCH != arm64 ]]; then
  echo "error: this native compositor package is for arm64; host is $ARCH" >&2
  exit 1
fi

mkdir -p "$OUTDIR/debian/pantheon-rust-compositor"
PACKAGE_ROOT="$OUTDIR/debian/pantheon-rust-compositor"
VERSION=${DEB_VERSION:-0.1.0+git$(git -C "$ROOT" rev-parse --short HEAD)}

cargo build --release --manifest-path "$ROOT/rust/Cargo.toml" \
  -p pantheon-compositor --bin pantheon-compositor --features native-drm

BIN="$ROOT/rust/target/release/pantheon-compositor"
[[ -x $BIN ]] || { echo "error: compositor build produced no executable" >&2; exit 1; }
if ldd "$BIN" | grep -q 'not found'; then
  echo "error: compositor binary has unresolved shared libraries" >&2
  exit 1
fi

install -D -m 0755 "$BIN" "$PACKAGE_ROOT/usr/bin/pantheon-compositor"
cp -a "$ROOT/mseries/pantheon-rust-compositor/session/usr/." "$PACKAGE_ROOT/usr/"
find "$PACKAGE_ROOT" -type d -exec chmod 0755 {} +
find "$PACKAGE_ROOT" -type f -exec chmod 0644 {} +
chmod 0755 "$PACKAGE_ROOT/usr/bin/pantheon-compositor"

cat > "$OUTDIR/debian/control" <<'EOF'
Source: pantheon-rust-compositor
Section: x11
Priority: optional
Maintainer: techmore <sdolbec1@gmail.com>
Standards-Version: 4.6.2

Package: pantheon-rust-compositor
Architecture: arm64
Description: experimental Rust compositor for the Pantheon M-series session
 An opt-in Smithay Wayland compositor and a separate experimental GNOME session.
EOF

SHLIB_DEPENDS=$(cd "$OUTDIR" && dpkg-shlibdeps -O \
  --package=pantheon-rust-compositor -Sdebian/pantheon-rust-compositor \
  debian/pantheon-rust-compositor/usr/bin/pantheon-compositor \
  | sed -n 's/^shlibs:Depends=//p')
if [[ -z $SHLIB_DEPENDS ]]; then
  echo "error: dpkg-shlibdeps returned no runtime dependencies" >&2
  exit 1
fi

mkdir -p "$PACKAGE_ROOT/DEBIAN"
cat > "$PACKAGE_ROOT/DEBIAN/control" <<EOF
Package: pantheon-rust-compositor
Version: $VERSION
Architecture: arm64
Maintainer: techmore <sdolbec1@gmail.com>
Depends: $SHLIB_DEPENDS, gnome-session, gtklock, libegl1, libgles2
Description: experimental Rust compositor for the Pantheon M-series session
 An opt-in Smithay Wayland compositor and a separate experimental GNOME session.
EOF

dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" \
  "$OUTDIR/pantheon-rust-compositor_${VERSION}_arm64.deb"
dpkg-deb --info "$OUTDIR/pantheon-rust-compositor_${VERSION}_arm64.deb"
