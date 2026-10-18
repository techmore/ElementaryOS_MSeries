#!/usr/bin/env bash
# UCM profile for sound through the external display (dock TV / HDMI) on the Aurora kernel. EXPERIMENTAL.
#   install-dcp-display-audio.sh            install the apple_dcp UCM profile
#   install-dcp-display-audio.sh --uninstall
# Inert until the kernel creates the `apple_dcp` sound card, which it does only when booted with
# appledrm.hdmi_audio=1 (not set by this script; that is a boot-entry change). See mseries/audio/DOCK-TV-AUDIO.md.
set -euo pipefail
here=$(dirname "$(readlink -f "$0")")
ucm=/usr/share/alsa/ucm2/conf.d/apple_dcp
if [[ ${1:-} == --uninstall ]]; then sudo rm -rf "$ucm"; echo "Removed $ucm"; exit 0; fi
sudo install -d -m 0755 "$ucm"
sudo install -m 0644 "$here/ucm/apple_dcp/apple_dcp.conf" "$here/ucm/apple_dcp/HiFi.conf" "$ucm/"
echo "UCM profile installed in $ucm"
