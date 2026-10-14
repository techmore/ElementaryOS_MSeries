#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
source_dir="${TORRENTIAL_SOURCE_DIR:-}"
output_dir="${TORRENTIAL_OUTPUT_DIR:-$repo_root/build/torrential-native}"
package_root="$output_dir/package"

if [[ -z "$source_dir" || ! -f "$source_dir/Cargo.toml" ]]; then
  echo 'Set TORRENTIAL_SOURCE_DIR to a checkout of davidmhewitt/torrential.' >&2
  exit 2
fi

for command in cargo dpkg-deb glib-compile-schemas; do
  command -v "$command" >/dev/null || { echo "Missing build tool: $command" >&2; exit 2; }
done

expected_commit=3af2c2ab473d074bb95a63a3bb185d5809ee8d8a
actual_commit="$(git -C "$source_dir" rev-parse HEAD 2>/dev/null || true)"
if [[ -z "$actual_commit" ]] || ! git -C "$source_dir" merge-base --is-ancestor "$expected_commit" HEAD; then
  echo "Source must descend from upstream commit $expected_commit; found ${actual_commit:-not a Git checkout}." >&2
  exit 2
fi

if [[ -e "$source_dir/LICENSE" || -e "$source_dir/COPYING" || -e "$source_dir/NOTICE" ]]; then
  echo 'Upstream licensing changed; review it before packaging this snapshot.' >&2
  exit 2
fi

arch="$(dpkg --print-architecture)"
version=0.1.0-1~mseries3
package_name=elementary-torrential
binary_name=torrential-relm4
target_dir="${CARGO_TARGET_DIR:-$source_dir/target}"

(
  cd "$source_dir"
  CARGO_TARGET_DIR="$target_dir" cargo build --release --locked
)

rm -rf "$package_root"
install -d "$package_root/DEBIAN" \
  "$package_root/usr/bin" \
  "$package_root/usr/share/applications" \
  "$package_root/usr/share/glib-2.0/schemas" \
  "$package_root/usr/share/icons/hicolor/scalable/apps" \
  "$package_root/usr/share/metainfo"

install -D -m 0644 "$repo_root/mseries/torrential-native/apparmor-torrential" \
  "$package_root/etc/apparmor.d/local/mseries-torrential"
install -m 0755 "$target_dir/release/$binary_name" "$package_root/usr/bin/$binary_name"
install -m 0644 "$source_dir/data/com.github.davidmhewitt.torrential.gschema.xml" \
  "$package_root/usr/share/glib-2.0/schemas/com.github.davidmhewitt.torrential.gschema.xml"
install -m 0644 "$repo_root/mseries/torrential-native/com.github.davidmhewitt.torrential.desktop" \
  "$package_root/usr/share/applications/com.github.davidmhewitt.torrential.desktop"
install -m 0644 "$repo_root/mseries/torrential-native/com.github.davidmhewitt.torrential.svg" \
  "$package_root/usr/share/icons/hicolor/scalable/apps/com.github.davidmhewitt.torrential.svg"
install -m 0644 "$repo_root/mseries/torrential-native/com.github.davidmhewitt.torrential.metainfo.xml" \
  "$package_root/usr/share/metainfo/com.github.davidmhewitt.torrential.metainfo.xml"

cat >"$package_root/DEBIAN/control" <<EOF
Package: $package_name
Version: $version
Section: net
Priority: optional
Architecture: $arch
Depends: transmission-daemon (>= 4.0), libgtk-4-1, libgranite7 | libgranite-7-7, libssl3t64
Maintainer: elementaryos-mseries local build
Description: Native elementary OS BitTorrent client
 GTK 4, Granite, and Rust desktop application using Transmission.
EOF

cat >"$package_root/DEBIAN/postinst" <<'EOF'
#!/bin/sh
set -e
glib-compile-schemas /usr/share/glib-2.0/schemas
if [ -f /etc/apparmor.d/transmission ] && command -v apparmor_parser >/dev/null; then
  mkdir -p /etc/apparmor.d/local
  touch /etc/apparmor.d/local/transmission-daemon
  if ! grep -Fqx 'include if exists <local/mseries-torrential>' /etc/apparmor.d/local/transmission-daemon; then
    printf '\ninclude if exists <local/mseries-torrential>\n' >> /etc/apparmor.d/local/transmission-daemon
  fi
  apparmor_parser -r /etc/apparmor.d/transmission
fi
exit 0
EOF
cat >"$package_root/DEBIAN/postrm" <<'EOF'
#!/bin/sh
set -e
case "$1" in
  remove|purge)
    if [ -f /etc/apparmor.d/local/transmission-daemon ]; then
      sed -i '\|^include if exists <local/mseries-torrential>$|d' /etc/apparmor.d/local/transmission-daemon
    fi
    if [ -f /etc/apparmor.d/transmission ] && command -v apparmor_parser >/dev/null; then
      apparmor_parser -r /etc/apparmor.d/transmission
    fi
    ;;
esac
exit 0
EOF
chmod 0755 "$package_root/DEBIAN/postinst" "$package_root/DEBIAN/postrm"

mkdir -p "$output_dir"
dpkg-deb --root-owner-group --build "$package_root" \
  "$output_dir/${package_name}_${version}_${arch}.deb"
printf 'Built native package: %s\n' "$output_dir/${package_name}_${version}_${arch}.deb"
