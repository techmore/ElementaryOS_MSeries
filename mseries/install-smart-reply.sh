#!/usr/bin/env bash
# Install Smart Reply per user (Rust): the `mseries-reply` binary, its input service and the Ctrl+Alt+R shortcut.
# Replaces the first Python slice in place: same unit name, same shortcut path, same rules file. No sudo.
#
#   bash mseries/install-smart-reply.sh               build, install, enable and (re)start the input service
#   bash mseries/install-smart-reply.sh --no-build    install an already built release binary
#   bash mseries/install-smart-reply.sh --uninstall   remove it (your rules file is kept)
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src="$repo/mseries/smart-reply"
bin="$HOME/.local/bin"
units="$HOME/.config/systemd/user"
old_share="$HOME/.local/share/mseries/smart-reply"
path=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/mseries-smartreply0/

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-smart-reply-input.service 2>/dev/null || true
  rm -f "$units/mseries-smart-reply-input.service" "$bin/mseries-reply" "$bin/mseries-smart-reply"
  rm -rf "$old_share"
  python3 - "$path" <<'PY'
import sys
from gi.repository import Gio
s = Gio.Settings.new("org.gnome.settings-daemon.plugins.media-keys")
s.set_strv("custom-keybindings", [p for p in s.get_strv("custom-keybindings") if p != sys.argv[1]])
Gio.Settings.sync()
PY
  systemctl --user daemon-reload
  echo 'Removed Smart Reply. Your rules file ~/.config/mseries/smart-reply.json was kept.'
  exit 0
fi

target=${CARGO_TARGET_DIR:-$(cargo metadata --format-version 1 --no-deps --manifest-path "$repo/rust/Cargo.toml" | python3 -c 'import json,sys; print(json.load(sys.stdin)["target_directory"])')}
if [[ ${1:-} != --no-build ]]; then
  CARGO_TARGET_DIR=$target cargo build --locked --release --manifest-path "$repo/rust/Cargo.toml" -p mseries-reply
fi
[[ -x $target/release/mseries-reply ]] || { echo "error: $target/release/mseries-reply is missing; build first" >&2; exit 1; }

install -Dm0755 "$target/release/mseries-reply" "$bin/mseries-reply"
# `mseries-smart-reply` is the command the shortcut runs. It must be a plain path with no arguments: with
# `mseries-reply trigger` as the shortcut command the settings daemon never launched it.
printf '#!/bin/sh\nexec "%s/mseries-reply" trigger "$@"\n' "$bin" > "$bin/mseries-smart-reply"
chmod 0755 "$bin/mseries-smart-reply"
install -Dm0644 "$src/mseries-smart-reply-input.service" "$units/mseries-smart-reply-input.service"
rm -rf "$old_share"   # the Python input service and core, now replaced

# Writes the default rules file only if there is none, so an edited file is never touched.
"$bin/mseries-reply" init-rules

python3 - "$path" "$bin/mseries-smart-reply" <<'PY'
import sys
from gi.repository import Gio
MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
custom = Gio.Settings.new_with_path(MEDIA + ".custom-keybinding", sys.argv[1])
custom.set_string("name", "Smart Reply")
custom.set_string("command", sys.argv[2])
if not custom.get_string("binding"):
    custom.set_string("binding", "<Control><Alt>r")   # physical Command+Option+R where Command is swapped with Ctrl
s = Gio.Settings.new(MEDIA)
existing = s.get_strv("custom-keybindings")
if sys.argv[1] not in existing:
    s.set_strv("custom-keybindings", existing + [sys.argv[1]])
Gio.Settings.sync()
PY
systemctl --user daemon-reload
systemctl --user enable mseries-smart-reply-input.service
systemctl --user restart mseries-smart-reply-input.service
echo 'Installed Smart Reply. Click into a chat reply box and press Ctrl+Alt+R. Tab inserts, Esc discards.'
echo 'Rules: ~/.config/mseries/smart-reply.json (allow list of chat apps; edit to add or block apps and contacts).'
