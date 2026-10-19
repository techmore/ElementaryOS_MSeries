#!/usr/bin/env bash
# Quieter system sounds: a small "mseries" sound theme that inherits elementary and
# replaces the volume-change chime with a scaled-down copy of the stock one.
#
#   bash mseries/install-quieter-sound-theme.sh [--gain-db N]   # for your user (default)
#   sudo bash mseries/install-quieter-sound-theme.sh --system   # for all users
#   bash mseries/install-quieter-sound-theme.sh --uninstall [--system]
#
# The default -10 dB makes the chime about half as loud as the stock one (peak drops
# from -11 dBFS to about -21 dBFS). Only the volume-change chime is touched; every
# other sound still comes from the elementary theme through Inherits.
set -euo pipefail

gain_db=-10
mode=user
action=install
source_wav=${MSERIES_SOUND_SOURCE:-/usr/share/sounds/elementary/stereo/audio-volume-change.wav}

while [[ $# -gt 0 ]]; do
  case $1 in
    --system) mode=system ;;
    --gain-db)
      gain_db=$2
      shift
      ;;
    --uninstall) action=uninstall ;;
    --help | -h)
      sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "Unknown option $1" >&2
      exit 1
      ;;
  esac
  shift
done

if [[ $mode == system ]]; then
  [[ $(id -u) == 0 ]] || { echo "--system needs to run as root (sudo)." >&2; exit 1; }
  theme_dir=/usr/share/sounds/mseries
  dconf_file=/etc/dconf/db/local.d/00-mseries-sound-theme
else
  theme_dir=${XDG_DATA_HOME:-$HOME/.local/share}/sounds/mseries
fi

set_theme() {
  command -v gsettings >/dev/null || return 0
  gsettings set org.gnome.desktop.sound theme-name "$1" 2>/dev/null || true
}

if [[ $action == uninstall ]]; then
  rm -rf "$theme_dir"
  if [[ $mode == system ]]; then
    rm -f "$dconf_file"
    command -v dconf >/dev/null && dconf update
    echo "Removed the system-wide mseries sound theme; sounds fall back to elementary."
  else
    current=$(gsettings get org.gnome.desktop.sound theme-name 2>/dev/null || true)
    [[ $current == "'mseries'" ]] && set_theme elementary
    echo "Removed your mseries sound theme; the volume chime is back to stock."
  fi
  exit 0
fi

[[ -f $source_wav ]] || {
  echo "Missing source chime: $source_wav (is io.elementary.sound-theme installed?)" >&2
  exit 1
}

mkdir -p "$theme_dir/stereo"
cat > "$theme_dir/index.theme" <<'EOF'
[Sound Theme]
Name=mseries
Directories=stereo
Inherits=elementary
EOF

python3 - "$source_wav" "$theme_dir/stereo/audio-volume-change.wav" "$gain_db" <<'PY'
import array
import sys
import wave

src, dst, gain_db = sys.argv[1], sys.argv[2], float(sys.argv[3])
with wave.open(src, "rb") as chime:
    params = chime.getparams()
    frames = chime.readframes(chime.getnframes())

if params.sampwidth != 2:
    sys.exit(f"expected 16-bit audio, got {params.sampwidth * 8}-bit")

gain = 10 ** (gain_db / 20)
samples = array.array("h")
samples.frombytes(frames)
if sys.byteorder == "big":
    samples.byteswap()

for i, sample in enumerate(samples):
    samples[i] = max(-32768, min(32767, int(sample * gain)))

if sys.byteorder == "big":
    samples.byteswap()

with wave.open(dst, "wb") as out:
    out.setparams(params)
    out.writeframes(samples.tobytes())

print(f"scaled chime by {gain_db:+.1f} dB -> {dst}")
PY

if [[ $mode == system ]]; then
  cat > "$dconf_file" <<'EOF'
# Quiet volume chime, installed by mseries/install-quieter-sound-theme.sh --system.
[org/gnome/desktop/sound]
theme-name='mseries'
EOF
  command -v dconf >/dev/null && dconf update
  echo "Installed the mseries sound theme system-wide (${gain_db} dB)."
  echo "Users who already chose a sound theme keep it; others get it at next login."
  echo "Revert: bash mseries/install-quieter-sound-theme.sh --uninstall --system"
else
  set_theme mseries
  echo "Installed your mseries sound theme (${gain_db} dB); it is active now."
  echo "Revert: bash mseries/install-quieter-sound-theme.sh --uninstall"
fi
