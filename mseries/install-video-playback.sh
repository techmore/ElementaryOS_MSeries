#!/usr/bin/env bash
# Opt-in hardware-decoded playback on the M-series port (needs install-video-decode.sh's VA-API driver first).
#
#   bash mseries/install-video-playback.sh                user level: mpv config + contained YouTube launcher
#   bash mseries/install-video-playback.sh --gstreamer    also apt-install GStreamer v4l2codecs (system-wide)
#   bash mseries/install-video-playback.sh --flatpak-videos  let the elementary Videos flatpak reach the decoder
#   bash mseries/install-video-playback.sh --status       show what is installed, change nothing
#   bash mseries/install-video-playback.sh --uninstall    remove what this script installed (user level)
#
# What each part does (see mseries/video-decode/README.md for the evidence):
# - mpv: ~/.config/mpv/mpv.conf = video-decode/mpv.conf (hwdec=vaapi-copy for H.264/HEVC/VP9) - only if you have
#   no mpv.conf yet; otherwise prints the include line to add yourself.
# - brave-youtube: ~/.local/bin/brave-youtube and a menu entry "YouTube (hardware decode, contained)". It is a
#   separate Brave profile in a bubblewrap container with Chromium's own sandbox off; your normal Brave is untouched.
# - --gstreamer: gstreamer1.0-plugins-bad (v4l2slh264dec/v4l2slh265dec/v4l2slvp9dec, rank primary+1, so every
#   GStreamer player - Totem, WebKitGTK video - autoplugs the AVD) and gstreamer1.0-libav (software fallback).
#   System-wide behaviour change, hence opt-in.
# - --flatpak-videos: Flatpak only offers --device=dri or --device=all; the AVD needs /dev/video* and /dev/media*,
#   so this grants io.elementary.videos --device=all (all device nodes). Its runtime ships v4l2codecs.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin=$HOME/.local/bin/brave-youtube
desk=$HOME/.local/share/applications/mseries-brave-youtube.desktop
mpvconf=${XDG_CONFIG_HOME:-$HOME/.config}/mpv/mpv.conf
marker='# mseries video-decode/mpv.conf'

status() {
  echo "VA-API driver : $(vainfo --display drm --device /dev/dri/renderD128 2>/dev/null | sed -n 's/.*Driver version: //p' || true)"
  echo "mpv.conf      : $( [[ -f $mpvconf ]] && { grep -qF "$marker" "$mpvconf" && echo "ours ($mpvconf)" || echo "yours, left alone ($mpvconf)"; } || echo none)"
  echo "brave-youtube : $( [[ -x $bin ]] && echo "$bin" || echo 'not installed') ; menu entry: $( [[ -f $desk ]] && sed -n 's/^Exec=//p' "$desk" || echo none)"
  echo "gst v4l2codecs: $(gst-inspect-1.0 v4l2codecs 2>/dev/null | grep -oE 'v4l2sl[a-z0-9]+dec' | tr '\n' ' ' || true)"
  if command -v flatpak >/dev/null && flatpak info io.elementary.videos >/dev/null 2>&1; then
    echo "Videos flatpak: installed, devices=$(flatpak info --show-permissions io.elementary.videos 2>/dev/null | sed -n 's/^devices=//p')"
  else echo 'Videos flatpak: not installed'; fi
}

case ${1:-} in
  --status) status; exit 0 ;;
  --uninstall)
    rm -f "$bin" "$desk"
    [[ -f $mpvconf ]] && grep -qF "$marker" "$mpvconf" && rm -f "$mpvconf"
    command -v flatpak >/dev/null && flatpak override --user --reset io.elementary.videos 2>/dev/null || true
    echo 'Removed the user-level playback setup (system packages, if installed with --gstreamer, are left).'
    exit 0 ;;
esac

vainfo --display drm --device /dev/dri/renderD128 2>/dev/null | grep -q VAProfileVP9Profile0 ||
  echo 'Warning: the VA-API driver does not list VP9 here; run mseries/install-video-decode.sh first.' >&2

# mpv
mkdir -p "$(dirname "$mpvconf")"
if [[ ! -e $mpvconf ]]; then
  { echo "$marker (installed $(date -I)); delete this file to go back to mpv defaults"; cat "$here/video-decode/mpv.conf"; } >"$mpvconf"
  echo "mpv: installed $mpvconf"
elif grep -qF "$marker" "$mpvconf"; then
  { echo "$marker (updated $(date -I)); delete this file to go back to mpv defaults"; cat "$here/video-decode/mpv.conf"; } >"$mpvconf"
  echo "mpv: updated $mpvconf"
else
  echo "mpv: you have your own $mpvconf; to use ours add this line to it:  include=\"$here/video-decode/mpv.conf\""
fi

# contained YouTube launcher
install -D -m 0755 "$here/video-decode/brave-youtube" "$bin"
sed "s|@BIN@|$bin|" "$here/video-decode/brave-youtube.desktop" | install -D -m 0644 /dev/stdin "$desk"
command -v update-desktop-database >/dev/null && update-desktop-database -q "$HOME/.local/share/applications" 2>/dev/null || true
echo "brave-youtube: $bin and menu entry $desk"

for arg in "$@"; do
  case $arg in
    --gstreamer)
      sudo apt-get install -y --no-install-recommends gstreamer1.0-plugins-bad gstreamer1.0-libav
      gst-inspect-1.0 v4l2codecs | grep -E 'v4l2sl.*dec:' ;;
    --flatpak-videos)
      flatpak info io.elementary.videos >/dev/null 2>&1 ||
        { echo 'io.elementary.videos is not installed (AppCenter or: flatpak install appcenter io.elementary.videos)' >&2; continue; }
      flatpak override --user --device=all io.elementary.videos
      echo 'Videos flatpak: granted --device=all (undo: flatpak override --user --reset io.elementary.videos)' ;;
    *) echo "unknown option $arg" >&2; exit 2 ;;
  esac
done
status
