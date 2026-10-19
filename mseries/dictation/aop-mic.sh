#!/usr/bin/env bash
# Built-in MacBook microphone as a PipeWire source (used by the Voxtype fallback only).
# The Apple AOP array (ALSA hw:1,0) is raw: 3 channels, 48 kHz, 32-bit FLOAT whatever format is
# asked for (the driver advertises every format and never converts), room noise near -80 dBFS and
# speech near -45 dBFS. ffmpeg must be told pcm_f32le: its s16le default turns the floats into noise.
# This mixes the channels, removes rumble, adds gain and publishes "MacBook Built-in Mic" at 16 kHz.
# node.autoconnect=false: the stream must never be linked to a speaker sink.
set -euo pipefail
card=${AOP_MIC_DEVICE:-hw:1,0}
gain=${AOP_MIC_GAIN:-60}
filter="pan=mono|c0=0.333*c0+0.333*c1+0.333*c2,highpass=f=120,lowpass=f=7000,volume=$gain,alimiter=limit=0.9,aresample=async=1"
ffmpeg -nostdin -v error -f alsa -c:a pcm_f32le -channels 3 -sample_rate 48000 -i "$card" \
  -af "$filter" -ar 16000 -f s16le - |
  pw-cat --playback --raw --rate 16000 --channels 1 --format s16 \
    -P 'media.class=Audio/Source node.name=mseries-builtin-mic node.autoconnect=false node.description="MacBook Built-in Mic"' -
