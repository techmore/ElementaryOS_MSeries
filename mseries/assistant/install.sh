#!/usr/bin/env bash
# Install the on-device assistant, milestone 1: the LFM3-Audio model service and F6 inline suggestions. No sudo.
#
#   bash mseries/assistant/install.sh              venv (if missing), model check, service, mseries-reply, F6 shortcut
#   bash mseries/assistant/install.sh --uninstall  remove the service and the F6 shortcut (model and venv are kept)
#
# The model (2.5 GB) is not downloaded unless --download-model is given.
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
here="$repo/mseries/assistant"
units="$HOME/.config/systemd/user"
libexec="$HOME/.local/libexec/mseries-assistant"
bin="$HOME/.local/bin"
mlx="$HOME/.local/share/mlx-omarchy"
venv="$HOME/.local/share/mseries-ai/lfm3-audio-venv"
model="$HOME/.cache/mseries-metal2vk/lfm3-audio-2b-8bit"
model_repo=LiquidAI/LFM3-Audio-2B-MLX-8bit
model_rev=22d2992154da0c0171c2c30710cc68d211e7e8e4
# mlx-vlm main at the merge of "Add LFM3-Audio support" (Blaizzy/mlx-vlm#2609); no release carries it yet.
mlx_vlm_rev=efd4b9f1e439361b01ff18a73d12f50a14e40990
path=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/mseries-suggest0/

keybinding() {  # $1 = add|remove
  python3 - "$1" "$path" "$bin/mseries-suggest" <<'PY'
import sys
from gi.repository import Gio
MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
action, path, command = sys.argv[1:]
s = Gio.Settings.new(MEDIA)
existing = [p for p in s.get_strv("custom-keybindings") if p != path]
if action == "add":
    custom = Gio.Settings.new_with_path(MEDIA + ".custom-keybinding", path)
    custom.set_string("name", "Inline suggestion")
    custom.set_string("command", command)
    if not custom.get_string("binding"):
        custom.set_string("binding", "F6")   # F5 is dictation, as on a Mac
    existing.append(path)
s.set_strv("custom-keybindings", existing)
Gio.Settings.sync()
PY
}

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-assistd.service 2>/dev/null || true
  rm -f "$units/mseries-assistd.service" "$bin/mseries-suggest"
  rm -rf "$libexec"
  keybinding remove
  systemctl --user daemon-reload
  echo "Removed the assistant service and F6. Kept: $venv and $model."
  exit 0
fi

[[ -x $mlx/venv/bin/python ]] || { echo "error: the private MLX runtime is missing ($mlx); run mseries/local-ai/install-assistants.sh --runtime" >&2; exit 1; }

if [[ ! -x $venv/bin/python ]]; then
  # An overlay venv: mlx-vlm and a few small packages on top of the private Vulkan MLX, which stays untouched.
  "$mlx/venv/bin/python" -m venv --without-pip "$venv"
  site=$("$venv/bin/python" -c 'import site; print(site.getsitepackages()[0])')
  echo "$mlx/venv/lib/python3.14/site-packages" > "$site/mlx-omarchy.pth"
fi
pip=("$mlx/venv/bin/python" -m pip --python "$venv/bin/python" install -q)
"$venv/bin/python" -c 'import mlx_vlm.models.lfm3_audio' 2>/dev/null || {
  # --no-deps everywhere a package could pull a stock mlx over the private build.
  "${pip[@]}" --no-deps "git+https://github.com/Blaizzy/mlx-vlm@$mlx_vlm_rev" mlx-audio
  "${pip[@]}" requests pillow miniaudio
}

if [[ ! -f $model/model.safetensors ]]; then
  if [[ ${1:-} != --download-model ]]; then
    echo "error: $model is missing. Re-run with --download-model to fetch $model_repo (2.5 GB)." >&2
    exit 1
  fi
  base="https://huggingface.co/$model_repo/resolve/$model_rev"
  files=$(curl -sf "https://huggingface.co/api/models/$model_repo/revision/$model_rev" \
          | python3 -c 'import json,sys; print("\n".join(s["rfilename"] for s in json.load(sys.stdin)["siblings"] if not s["rfilename"].startswith(".")))')
  while read -r f; do
    mkdir -p "$model/$(dirname "$f")"
    curl -sSfL --retry 3 -C - -o "$model/$f" "$base/$f"
  done <<< "$files"
fi

install -Dm0644 "$here/assistd.py" "$libexec/assistd.py"
install -Dm0644 "$here/mseries-assistd.service" "$units/mseries-assistd.service"

# mseries-reply carries the F6 command; the Smart Reply installer builds it and (re)starts its input service.
bash "$repo/mseries/install-smart-reply.sh" "${@:2}"
# The shortcut command must be a plain path without arguments (see install-smart-reply.sh).
printf '#!/bin/sh\nexec "%s/mseries-reply" suggest "$@"\n' "$bin" > "$bin/mseries-suggest"
chmod 0755 "$bin/mseries-suggest"
keybinding add

systemctl --user daemon-reload
systemctl --user enable mseries-assistd.service
systemctl --user restart mseries-assistd.service
echo 'Installed. In any text field: type a few words, press F6, then Tab to insert the suggestion (Esc discards).'
echo 'F5 stays dictation. Model API: http://127.0.0.1:8772 (see mseries/assistant/README.md).'
