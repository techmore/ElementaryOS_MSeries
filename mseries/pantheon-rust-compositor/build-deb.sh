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
# Epoch 1 plus a commit-time stamp: every later build sorts above every earlier
# one under dpkg (the old bare 0.1.0+git<hash> scheme did not), so apt or an
# image build can never pick an older package and revert fixes.
STAMP=$(TZ=UTC git -C "$ROOT" show -s --format=%cd --date=format:%Y%m%d%H%M%S HEAD)
VERSION=${DEB_VERSION:-1:0.1.0+git${STAMP}.$(git -C "$ROOT" rev-parse --short=7 HEAD)}
FILE_VERSION=${VERSION#*:}

cargo build --release --locked --manifest-path "$ROOT/rust/Cargo.toml" \
  -p pantheon-compositor --bin pantheon-compositor --features native-drm

# Honor a shared Cargo target directory so isolated worktrees can reuse builds.
TARGET_DIR=$(cargo metadata --manifest-path "$ROOT/rust/Cargo.toml" --locked --no-deps --format-version 1 | python3 -c 'import json,sys; print(json.load(sys.stdin)["target_directory"])')
BIN="$TARGET_DIR/release/pantheon-compositor"
[[ -x $BIN ]] || { echo "error: compositor build produced no executable" >&2; exit 1; }
if ldd "$BIN" | grep -q 'not found'; then
  echo "error: compositor binary has unresolved shared libraries" >&2
  exit 1
fi

install -D -m 0755 "$BIN" "$PACKAGE_ROOT/usr/bin/pantheon-compositor"
cp -a "$ROOT/mseries/pantheon-rust-compositor/session/usr/." "$PACKAGE_ROOT/usr/"
install -D -m 0755 "$ROOT/mseries/window-recovery/restore-windows.py" "$PACKAGE_ROOT/usr/bin/mseries-restore-windows"
install -D -m 0644 "$ROOT/mseries/window-recovery/mseries-restore-windows.desktop" "$PACKAGE_ROOT/usr/share/applications/mseries-restore-windows.desktop"
find "$PACKAGE_ROOT" -type d -exec chmod 0755 {} +
find "$PACKAGE_ROOT" -type f -exec chmod 0644 {} +
chmod 0755 "$PACKAGE_ROOT/usr/bin/pantheon-compositor"
chmod 0755 "$PACKAGE_ROOT/usr/bin/pantheon-rust-session"
chmod 0755 "$PACKAGE_ROOT/usr/bin/pantheon-rust-dock"
chmod 0755 "$PACKAGE_ROOT/usr/bin/mseries-restore-windows"

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
Depends: $SHLIB_DEPENDS, dbus-bin, gnome-session, gtklock, io.elementary.dock, io.elementary.wingpanel, libegl1, libgles2, xdg-desktop-portal, xwayland, python3-gi, zenity, pipewire-bin, sound-theme-freedesktop
Description: experimental Rust compositor for the Pantheon M-series session
 An opt-in Smithay Wayland compositor and a separate experimental GNOME session.
EOF

dpkg-deb --build --root-owner-group "$PACKAGE_ROOT" \
  "$OUTDIR/pantheon-rust-compositor_${FILE_VERSION}_arm64.deb"
dpkg-deb --info "$OUTDIR/pantheon-rust-compositor_${FILE_VERSION}_arm64.deb"
