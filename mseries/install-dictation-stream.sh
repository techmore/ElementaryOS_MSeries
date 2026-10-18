#!/usr/bin/env bash
# Streaming F5 dictation: transcribe.cpp 0.4.0 (MIT) + Parakeet Unified 0.6B Q4_K_M (CC-BY-4.0).
# Needs install-dictation.sh first (F5 remap, mic bridge, ydotool). Replaces the Voxtype service,
# which stays installed as the fallback: `systemctl --user start voxtype` (the units conflict).
#   --uninstall   stop streaming, re-enable Voxtype
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/dictation
base=$HOME/.local/share/mseries/stream
rel=https://github.com/handy-computer/transcribe.cpp/releases/download/v0.4.0
tarball=transcribe-native-0.4.0-linux-aarch64-cpu-vulkan.tar.gz
tar_sha=af7ee108923b74d3e727309ce4992714a25872ea77c6247da8be9a0ed54275dd
whl=transcribe_cpp-0.4.0-py3-none-any.whl
whl_sha=c6dd091848006c7881d46b4066aa687782f49302c4253c0cb45396976cb0abcd
model=parakeet-unified-en-0.6b-Q4_K_M.gguf
model_sha=a8bf3de2b393bd14ead5a858c3748d5e3b07a20fdeabdd3b498fba4f463fa929
model_url=https://huggingface.co/handy-computer/parakeet-unified-en-0.6b-gguf/resolve/main/$model
[[ $EUID != 0 ]] || { echo 'Run as your normal user.' >&2; exit 2; }

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-stream-dictate.service 2>/dev/null || true
  rm -f ~/.config/systemd/user/mseries-stream-dictate.service
  systemctl --user enable --now voxtype.service 2>/dev/null || true
  exit 0
fi
[[ -x /usr/local/bin/voxtype ]] || { echo 'Run mseries/install-dictation.sh first.' >&2; exit 1; }

fetch() { # url file sha
  [[ -f $2 ]] && echo "$3  $2" | sha256sum -c --quiet 2>/dev/null && return 0
  curl -fL --proto '=https' -o "$2" "$1"
  echo "$3  $2" | sha256sum -c --quiet
}
mkdir -p "$base/dl" "$base/models" "$base/native"
cd "$base"
fetch "$rel/$tarball" "dl/$tarball" "$tar_sha"
fetch "$rel/$whl" "dl/$whl" "$whl_sha"
fetch "$model_url" "models/$model" "$model_sha"
tar xzf "dl/$tarball" -C native
[[ -d venv ]] || python3 -m venv venv
./venv/bin/pip install -q numpy "dl/$whl"
install -m755 "$here/stream-dictate.py" stream-dictate.py
install -m644 "$here/mseries-stream-dictate.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable --now voxtype.service 2>/dev/null || true
systemctl --user enable --now mseries-stream-dictate.service
echo 'Streaming dictation ready: hold F5, speak; words appear as you talk.'
