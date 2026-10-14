#!/usr/bin/env bash
# Install or remove the pinned upstream Tether ARM64 package on elementary OS.
# This does not configure Bluetooth, open firewall ports, enable tetherd, or
# install/enable a browser extension.
set -euo pipefail

VERSION='0.2.38'
PACKAGE='tether'
ASSET="tether_${VERSION}_arm64.deb"
SHA256='eec8892093cbca2062739080f381a594006f9437abd1374f2087b936877257ae'
DOWNLOAD_URL="https://github.com/zackb/tether/releases/download/v${VERSION}/${ASSET}"

usage() {
  cat <<'EOF'
Usage:
  bash mseries/install-tether.sh             Install the pinned ARM64 package
  bash mseries/install-tether.sh --status     Show package and Bluetooth readiness
  bash mseries/install-tether.sh --uninstall  Remove the package, keep user data
  bash mseries/install-tether.sh --purge-data Remove Tether XDG config/data/state

The installer checks the upstream release SHA-256 and asks apt to install the
local package. It never enables services, changes Bluetooth configuration,
opens firewall ports, or installs a browser extension.
EOF
}

bluetooth_version() {
  if command -v bluetoothd >/dev/null 2>&1; then
    bluetoothd -v 2>/dev/null | head -n1 || true
  elif dpkg-query -W -f='${Version}' bluez 2>/dev/null; then
    :
  fi
}

show_status() {
  if dpkg-query -W -f='${Status} ${Version} ${Architecture}\n' "$PACKAGE" 2>/dev/null | grep -q '^install ok installed'; then
    printf 'Tether: '
    dpkg-query -W -f='${Version} (${Architecture})\n' "$PACKAGE"
  else
    echo 'Tether: not installed'
  fi

  local version
  version="$(bluetooth_version)"
  if [[ -z "$version" ]]; then
    echo 'BlueZ: not detected; Bluetooth messages are unavailable.'
  elif dpkg --compare-versions "$version" ge 5.86; then
    printf 'BlueZ: %s (meets Tether minimum; experimental bearer setup is still required)\n' "$version"
  else
    printf 'BlueZ: %s (Tether messages require 5.86+; no upgrade was attempted)\n' "$version"
  fi
}

install_package() {
  [[ "$(dpkg --print-architecture)" == 'arm64' ]] || {
    echo 'This pinned integration currently supports the ARM64 elementary M-series target only.' >&2
    exit 1
  }
  [[ "$(. /etc/os-release; printf '%s' "${ID:-}")" == 'elementary' ]] || {
    echo 'This installer is scoped to elementary OS.' >&2
    exit 1
  }
  command -v curl >/dev/null 2>&1 || { echo 'curl is required.' >&2; exit 1; }
  command -v sha256sum >/dev/null 2>&1 || { echo 'sha256sum is required.' >&2; exit 1; }
  command -v apt-get >/dev/null 2>&1 || { echo 'apt-get is required.' >&2; exit 1; }

  local workdir package_file
  workdir="$(mktemp -d)"
  trap 'rm -rf -- "$workdir"' EXIT
  package_file="$workdir/$ASSET"
  curl --fail --location --retry 2 --output "$package_file" "$DOWNLOAD_URL"
  printf '%s  %s\n' "$SHA256" "$package_file" | sha256sum --check --status || {
    echo 'Downloaded Tether package checksum did not match the pinned upstream release digest.' >&2
    exit 1
  }
  echo "Verified upstream Tether $VERSION ARM64 package (SHA-256 $SHA256)."
  echo 'Apt will show any required system package changes before applying them.'
  (cd "$workdir" && sudo apt-get install "./$ASSET")

  echo
  show_status
  cat <<'EOF'

Next steps:
  1. Launch Tether from Applications or run tether-gtk.
  2. Install “Tether - Linux Companion” from the iOS App Store.
  3. Pair explicitly in the app on both devices.
  4. For Brave OTP handoff, follow mseries/tether/README.md. Extension install
     is separate and asks for broad website access.

For Wi-Fi pairing, Tether uses TCP 5134 and mDNS/UDP 5353. This installer does
not open those ports. For Bluetooth Messages, run tether bt setup and review
its commands yourself; Tether requires BlueZ 5.86+ with the experimental
bearer API. The daemon is not enabled as a background service by this script.
EOF
}

uninstall_package() {
  if ! dpkg-query -W -f='${Status}' "$PACKAGE" 2>/dev/null | grep -q '^install ok installed'; then
    echo 'Tether is not installed.'
    return
  fi
  if systemctl --user is-enabled --quiet tetherd.service 2>/dev/null; then
    systemctl --user disable --now tetherd.service
  else
    systemctl --user stop tetherd.service 2>/dev/null || true
  fi
  sudo apt-get remove tether
  echo 'Tether package removed. Pairing and user data were kept.'
  echo 'Remove a Brave registration with: python3 mseries/tether/brave-extension.py unregister EXTENSION_ID'
}

purge_data() {
  echo 'This removes Tether XDG config/data/state only; it does not remove the package, browser extension, or OS Bluetooth bond.'
  for path in \
    "${XDG_CONFIG_HOME:-$HOME/.config}/tether" \
    "${XDG_DATA_HOME:-$HOME/.local/share}/tether" \
    "${XDG_STATE_HOME:-$HOME/.local/state}/tether"; do
    if [[ -e "$path" ]]; then
      printf 'Removing %s\n' "$path"
      rm -rf -- "$path"
    fi
  done
}

case "${1:-install}" in
  install) install_package ;;
  --status) show_status ;;
  --uninstall) uninstall_package ;;
  --purge-data) purge_data ;;
  --help|-h) usage ;;
  *) usage >&2; exit 2 ;;
esac
