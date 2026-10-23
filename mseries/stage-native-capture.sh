#!/usr/bin/env bash
# Verify the tested screenshot release; install only with explicit --install.
# Installing stages the binary for next login and never restarts the desktop.
set -euo pipefail
root=$(cd -- "$(dirname -- "$(readlink -f -- "${BASH_SOURCE[0]}")")/.." && pwd)
package="$root/build/screenshot-native-capability/pantheon-rust-compositor_0.1.0+gitb2887485_arm64.deb"
expected=4ef4a735610980e0d67085a6577ef9ddcc7969d5e29e02e8d0cb0d03e4d520a7
case ${1:---verify} in
  --verify|--install) action=${1:---verify} ;;
  *) echo "Usage: $0 [--verify|--install]" >&2; exit 2 ;;
esac
[[ $# -le 1 ]] || { echo 'Unexpected arguments' >&2; exit 2; }
[[ -f $package ]] || { echo "Missing tested package: $package" >&2; exit 1; }
actual=$(sha256sum -- "$package")
[[ ${actual%% *} == "$expected" ]] || { echo 'Package differs from the tested release; refusing installation.' >&2; exit 1; }
[[ $(dpkg-deb -f "$package" Package) == pantheon-rust-compositor ]]
[[ $(dpkg-deb -f "$package" Architecture) == "$(dpkg --print-architecture)" ]]
echo 'Verified the tested native screenshot package.'
if [[ $action == --install ]]; then
  sudo bash "$root/mseries/install-pantheon-rust-compositor.sh" --install --yes --deb "$package"
  echo 'Staged for your next login. The current desktop has not been restarted.'
else
  echo 'To stage it from your own terminal: mseries-stage-native-capture --install'
  echo 'A new login is required to load it.'
fi
