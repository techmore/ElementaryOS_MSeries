#!/usr/bin/env bash
# Let PipeWire find AirPlay (RAOP) speakers and Apple TVs on the network so they show up in the
# Quick Settings "Sound Output" list. Per-user drop-in; needs avahi-daemon (mDNS). Does not restart
# PipeWire: AirPlay devices appear after the next login or `systemctl --user restart pipewire`.
set -euo pipefail
src=/usr/share/pipewire/pipewire.conf.avail/50-raop.conf
dest="${XDG_CONFIG_HOME:-$HOME/.config}/pipewire/pipewire.conf.d/50-raop.conf"
if [[ ${1:-} == --uninstall ]]; then
  rm -f "$dest"
  echo 'AirPlay discovery removed. Restart PipeWire or log in again to apply.'
  exit
fi
[[ -r $src ]] || { echo "PipeWire RAOP config not found at $src (install pipewire-audio / libpipewire-0.3-modules)" >&2; exit 1; }
systemctl is-active --quiet avahi-daemon || echo 'warning: avahi-daemon is not running; AirPlay devices will not be discovered.' >&2
install -D -m644 "$src" "$dest"
echo "Installed $dest. Restart PipeWire or log in again to apply."
