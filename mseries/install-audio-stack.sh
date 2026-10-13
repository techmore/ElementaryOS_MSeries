#!/usr/bin/env bash
# Apple Silicon speaker support on the elementary side, from Ubuntu's archive.
#
#   bash mseries/install-audio-stack.sh            # speaker protection daemon only (safe default)
#   bash mseries/install-audio-stack.sh --with-dsp # + Apple UCM profile + asahi-audio DSP chain
#   bash mseries/install-audio-stack.sh --revert   # remove everything this script installs
#
# STATUS 2026-10-13: --with-dsp works once PipeWire has its LV2 filter plugin, which Ubuntu does not ship. Run
# mseries/install-pipewire-lv2.sh first (it builds that one plugin from the matching upstream source); this script
# refuses --with-dsp without it, because the speakers would otherwise disappear (2026-10-12 incident).
# The speaker sink then appears as "MacBook Pro J314 Speakers" (under Filters in wpctl status) and starts at the
# volume the old sink had, so lower the volume BEFORE installing and raise it slowly afterwards.
#
# Why: the elementary root had none of what the Arch/Omarchy root already runs. The kernel keeps the
# speakers volume-locked ("Speaker Volume Unlock"), but the amplifier (tas2764) logged recurring
# `fault: over current` and the generic profile sounds quiet and plain. speakersafetyd watches speaker
# temperature/excursion and clamps; asahi-audio adds the per-model DSP (crossover, EQ, bass).
#
# Versions: Ubuntu has speakersafetyd 1.1.2, asahi-audio 3.4, alsa-ucm-conf-asahi 8 (Arch: 2.0.1 / 4.1 / 10).
# The j314 speaker safety profile in speakersafetyd 1.1.2 is byte-identical to the Arch 2.0.1 one.
#
# SAFETY: a new virtual speaker sink can default to 100% volume. This script reads your default-sink
# volume first, restarts the audio services, and puts the volume straight back before anything can play.
# It never plays sound itself. After installing, start low and raise the volume slowly.
set -euo pipefail

with_dsp=0
dsp_pkgs=(asahi-audio alsa-ucm-conf-asahi)
lv2_plugin=/usr/lib/aarch64-linux-gnu/spa-0.2/filter-graph/libspa-filter-graph-plugin-lv2.so

# Real sinks list "[vol: ...]"; asahi-audio's virtual speaker sink sits under "Filters" as [Audio/Sink].
sink_ids() {
  wpctl status 2>/dev/null | sed -n '/^Audio/,/^Video/p' | grep -E '\[vol:|\[Audio/Sink\]' | grep -oE '^[ │├└─*-]*[0-9]+\.' | grep -oE '[0-9]+'
}

# Whatever happens, no sink may be left louder than the user had it.
remember_volume() {
  volume=$(wpctl get-volume @DEFAULT_AUDIO_SINK@ 2>/dev/null | awk '{print $2}')
  volume=${volume:-0.00}
}

restart_audio_and_restore_volume() {
  systemctl --user restart wireplumber pipewire pipewire-pulse
  for _ in $(seq 1 20); do wpctl status >/dev/null 2>&1 && break; sleep 0.5; done
  sleep 4   # card and sinks appear a few seconds after WirePlumber starts
  local id
  for id in $(sink_ids); do wpctl set-volume "$id" "$volume"; done
}

case ${1:-} in
  --with-dsp) with_dsp=1 ;;
  --revert)
    sudo apt-get remove -y speakersafetyd "${dsp_pkgs[@]}" bankstown-lv2 triforce-lv2 lsp-plugins-lv2 lsp-plugins-r3d-glx 2>/dev/null \
      || sudo apt-get remove -y speakersafetyd
    remember_volume
    restart_audio_and_restore_volume
    echo 'Removed.'
    exit 0 ;;
  '') ;;
  *) echo "unknown option $1" >&2; exit 1 ;;
esac

if (( with_dsp )) && [[ ! -e $lv2_plugin ]]; then
  echo "Refusing --with-dsp: $lv2_plugin is missing, so PipeWire cannot load asahi-audio's LV2 speaker chain." >&2
  echo "Run: bash mseries/install-pipewire-lv2.sh   (see the STATUS note at the top of this script)." >&2
  exit 1
fi

remember_volume
echo "current default sink volume: $volume"

sudo apt-get install -y speakersafetyd
(( with_dsp )) && sudo apt-get install -y "${dsp_pkgs[@]}"
sudo systemctl enable --now speakersafetyd.service
sudo udevadm trigger --subsystem-match=sound --action=change || true

if (( with_dsp )); then restart_audio_and_restore_volume; fi
echo "speakersafetyd: $(systemctl is-active speakersafetyd.service)"
wpctl status | sed -n '/Sinks:/,/Sources:/p' | head -6
