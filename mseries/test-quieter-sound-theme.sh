#!/usr/bin/env bash
# Hermetic test for install-quieter-sound-theme.sh: temporary HOME, a generated source
# chime, and a stubbed gsettings. No session, no root, no real sound theme needed.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
root=$(mktemp -d)
trap 'rm -rf "$root"' EXIT

mkdir -p "$root/home" "$root/bin"

cat > "$root/bin/gsettings" <<'STUB'
#!/usr/bin/env bash
echo "$*" >> "$HOME/gsettings.log"
if [[ ${1:-} == get ]]; then
  cat "$HOME/theme.value" 2>/dev/null || echo "'elementary'"
else
  printf "'%s'\n" "${@: -1}" > "$HOME/theme.value"
fi
STUB
chmod +x "$root/bin/gsettings"

python3 - "$root/chime.wav" <<'PY'
import math
import struct
import sys
import wave

with wave.open(sys.argv[1], "wb") as chime:
    chime.setnchannels(2)
    chime.setsampwidth(2)
    chime.setframerate(48000)
    frames = b"".join(
        struct.pack("<hh", int(30000 * math.sin(2 * math.pi * 440 * i / 48000)),
                    int(30000 * math.sin(2 * math.pi * 440 * i / 48000)))
        for i in range(4800)
    )
    chime.writeframes(frames)
PY

export HOME=$root/home
export PATH=$root/bin:$PATH
export MSERIES_SOUND_SOURCE=$root/chime.wav

fail() { echo "FAIL $1" >&2; exit 1; }

bash "$here/install-quieter-sound-theme.sh" --gain-db -10 >/dev/null
theme=$HOME/.local/share/sounds/mseries
[[ -f $theme/index.theme ]] || fail "index.theme missing"
[[ -f $theme/stereo/audio-volume-change.wav ]] || fail "scaled chime missing"
grep -qx 'Inherits=elementary' "$theme/index.theme" || fail "theme does not inherit elementary"
grep -q 'theme-name mseries' "$HOME/gsettings.log" || fail "sound theme was not selected"

python3 - "$root/chime.wav" "$theme/stereo/audio-volume-change.wav" <<'PY' || fail "chime is not quieter"
import array
import sys
import wave

def peak(path):
    with wave.open(path, "rb") as wav:
        samples = array.array("h")
        samples.frombytes(wav.readframes(wav.getnframes()))
    return max(abs(sample) for sample in samples)

src, dst = peak(sys.argv[1]), peak(sys.argv[2])
if not 0 < dst < src * 0.5:
    sys.exit(f"peaks are wrong: source {src}, theme {dst}")
print(f"peak {src} -> {dst}")
PY

# Second install is idempotent.
bash "$here/install-quieter-sound-theme.sh" >/dev/null

# Uninstall removes the theme and restores the elementary theme.
bash "$here/install-quieter-sound-theme.sh" --uninstall >/dev/null
[[ ! -e $theme ]] || fail "theme left installed"
grep -q 'theme-name elementary' "$HOME/gsettings.log" || fail "sound theme was not restored"

# Uninstall without gsettings state must not fail.
rm -f "$HOME/theme.value"
bash "$here/install-quieter-sound-theme.sh" --uninstall >/dev/null || fail "uninstall without theme set failed"

echo "quieter sound theme: ok"
