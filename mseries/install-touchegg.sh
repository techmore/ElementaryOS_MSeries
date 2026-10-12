#!/bin/bash
# Build and install the Touchegg gesture daemon that Gala reads for touchpad gestures.
# Touchegg is no longer packaged for Ubuntu 26.04 (resolute), so build the upstream release.
set -euo pipefail

version=2.0.18

if [[ ${1:-} == --uninstall ]]; then
  sudo systemctl disable --now touchegg || true
  sudo rm -f /usr/bin/touchegg /usr/lib/systemd/system/touchegg.service \
    /etc/xdg/autostart/touchegg.desktop
  sudo rm -rf /usr/share/touchegg
  sudo systemctl daemon-reload
  echo 'Removed Touchegg. Log out and back in so Gala stops looking for it.'
  exit 0
fi

sudo apt install cmake g++ git libinput-dev libudev-dev libpugixml-dev libcairo2-dev \
  libgtk-3-dev libx11-dev libxtst-dev libxrandr-dev libxi-dev libsystemd-dev systemd-dev

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/touchegg.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
git clone -q --depth 1 --branch "$version" https://github.com/JoseExposito/touchegg.git "$build_dir/src"
# CMake 4 rejects the project's old minimum-version declaration; 3.5 restores the old behaviour.
cmake -S "$build_dir/src" -B "$build_dir/build" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build "$build_dir/build" -j"$(nproc)"
sudo cmake --install "$build_dir/build"
# Gala handles gestures itself and only needs the daemon; the X11 client would act on the
# same swipes a second time.
sudo rm -f /etc/xdg/autostart/touchegg.desktop
sudo systemctl daemon-reload
sudo systemctl enable --now touchegg
echo 'Installed the Touchegg daemon. Log out and back in so Gala connects to it.'
