#!/usr/bin/env bash
# Streaming F5 dictation: transcribe.cpp 0.4.0 (MIT) + English Nemotron 0.6B Q8 streaming (model license in source card).
# Needs install-dictation.sh first (F5 remap, mic bridge, ydotool). Replaces the Voxtype service,
# which stays installed as the fallback: `systemctl --user start voxtype` (the units conflict).
#   --uninstall   stop streaming, re-enable Voxtype
#   --universal   activate focus-bound Unicode output after installing the runtime
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/dictation
base=$HOME/.local/share/mseries/stream
rel=https://github.com/handy-computer/transcribe.cpp/releases/download/v0.4.0
tarball=transcribe-native-0.4.0-linux-aarch64-cpu-vulkan.tar.gz
tar_sha=af7ee108923b74d3e727309ce4992714a25872ea77c6247da8be9a0ed54275dd
whl=transcribe_cpp-0.4.0-py3-none-any.whl
whl_sha=c6dd091848006c7881d46b4066aa687782f49302c4253c0cb45396976cb0abcd
model=nemotron-speech-streaming-en-0.6b-Q8_0.gguf
model_sha=90d8c89714cd31efc88be62a40c6b2bea57e0cc2063af1ffe2c28f1a228ca110
model_url=https://huggingface.co/handy-computer/nemotron-speech-streaming-en-0.6b-gguf/resolve/7df420cc3fb915a3b334560dac712af44fc41ef5/$model
numpy_version=2.5.4 # Qualified with transcribe.cpp 0.4.0 on this Python 3.14 ARM64 host.
[[ $EUID != 0 ]] || { echo 'Run as your normal user.' >&2; exit 2; }

if [[ ${1:-} == --uninstall ]]; then
  if [[ -f $base/dictation-manage.py ]]; then
    python3 "$base/dictation-manage.py" --rollback
  fi
  systemctl --user disable --now mseries-stream-dictate.service 2>/dev/null || true
  rm -f ~/.config/systemd/user/mseries-stream-dictate.service
  systemctl --user enable --now voxtype.service 2>/dev/null || true
  exit 0
fi
case ${1:-} in
  '') universal=false ;;
  --universal) universal=true ;;
  *) echo 'Use --universal, --uninstall, or no option.' >&2; exit 2 ;;
esac
if [[ -f $HOME/.local/state/mseries-dictation-input/baseline.json ]]; then
  unicode_current=$(python3 -c 'import json,sys; print(int(json.load(open(sys.argv[1]))["metadata"].get("activated", False)))' \
    "$HOME/.local/state/mseries-dictation-input/baseline.json")
  if [[ $unicode_current == 1 ]]; then
    universal=true # Preserve an already activated Unicode configuration on upgrade.
  fi
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
./venv/bin/pip install -q "numpy==$numpy_version" "dl/$whl"
if [[ $universal == false || ! -f stream-dictate.py ]]; then
  install -m755 "$here/stream-dictate.py" stream-dictate.py
  install -m644 "$here/dictation_status.py" dictation_status.py
  install -m644 "$here/dictation_resources.py" dictation_resources.py
  install -m644 "$here/dictation_model.py" dictation_model.py
  install -m644 "$here/dictation_media.py" dictation_media.py
  install -m644 "$here/dictation_ane.py" dictation_ane.py
  install -m644 "$here/ane-worker-shim.py" ane-worker-shim.py
  install -m644 "$here/../local-ai/machine.py" machine.py
fi
install -m644 "$here/mseries-stream-dictate.service" ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user disable --now voxtype.service 2>/dev/null || true
if [[ $universal == true ]]; then
  systemctl --user enable mseries-stream-dictate.service
  python3 "$here/../install-dictation-input.py" --activate
else
  systemctl --user enable --now mseries-stream-dictate.service
fi
echo 'Streaming dictation installed; inspect dictation/README.md for coverage and live F5 acceptance.'
