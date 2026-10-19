#!/usr/bin/env bash
set -euo pipefail

repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
for tool in meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool. Install build requirements with:" >&2
    echo "  sudo apt install meson ninja-build valac libwingpanel-9-dev" >&2
    exit 1
  }
done

build_dir="$(mktemp -d "${TMPDIR:-/tmp}/protonvpn-wingpanel.XXXXXX")"
trap 'rm -rf -- "$build_dir"' EXIT
meson setup "$build_dir" "$repo/mseries/protonvpn-wingpanel" --prefix=/usr
ninja -C "$build_dir"

indicators_dir="$(pkg-config --variable=indicatorsdir wingpanel-9)"
sudo install -D -m 0755 "$build_dir/libmseries-protonvpn.so" \
  "$indicators_dir/libmseries-protonvpn.so"

if pgrep -x io.elementary.w >/dev/null; then
  pkill -x io.elementary.w || true
  for _ in {1..10}; do
    pgrep -x io.elementary.w >/dev/null || break
    sleep 1
  done
fi
if ! pgrep -x io.elementary.w >/dev/null; then
  setsid -f io.elementary.wingpanel >/dev/null 2>&1
fi
for _ in {1..10}; do
  pgrep -x io.elementary.w >/dev/null && break
  sleep 1
done
pgrep -x io.elementary.w >/dev/null || {
  echo "Wingpanel did not restart after installing the Proton VPN indicator." >&2
  exit 1
}
echo "Installed and loaded Proton VPN's Wingpanel launcher. Click its top-panel icon to open the app."
