#!/bin/bash
# Build and install the Touchegg gesture daemon that Gala reads for touchpad gestures.
# Touchegg is no longer packaged for Ubuntu 26.04 (resolute), so build the upstream release.
set -euo pipefail

version=2.0.18
source_commit=fc30d316e163f4504043353d6610e670ce5c6439

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
git init -q "$build_dir/src"
git -C "$build_dir/src" remote add origin https://github.com/JoseExposito/touchegg.git
git -C "$build_dir/src" fetch -q --depth=1 origin "$source_commit"
git -C "$build_dir/src" checkout -q --detach FETCH_HEAD
# CMake 4 rejects the project's old minimum-version declaration; 3.5 restores the old behaviour.
source "$(dirname -- "${BASH_SOURCE[0]}")/lib-build.sh" 2>/dev/null && mseries_ccache_enable cmake || true   # optional ccache (#47)
cmake -S "$build_dir/src" -B "$build_dir/build" -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_INSTALL_PREFIX=/usr -DCMAKE_INSTALL_SYSCONFDIR=/etc -DCMAKE_POLICY_VERSION_MINIMUM=3.5
cmake --build "$build_dir/build" -j"$(nproc)"
sudo cmake --install "$build_dir/build"
# Gala handles gestures itself and only needs the daemon; the X11 client would act on the
# same swipes a second time.
sudo rm -f /etc/xdg/autostart/touchegg.desktop
sudo systemctl daemon-reload
sudo systemctl enable --now touchegg
echo "Installed Touchegg $version ($source_commit). Log out and back in so Gala connects to it."
