#!/usr/bin/env bash
# Install Smart Reply per user: input service, trigger command and the Ctrl+Alt+R shortcut.
# Needs the dictation input module (mseries-dictation-input) for its field-safety checks. No sudo.
set -euo pipefail
src="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/smart-reply" && pwd)"
share="$HOME/.local/share/mseries/smart-reply"
units="$HOME/.config/systemd/user"
path=/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings/mseries-smartreply0/

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now mseries-smart-reply-input.service 2>/dev/null || true
  rm -f "$units/mseries-smart-reply-input.service" "$HOME/.local/bin/mseries-smart-reply"
  rm -rf "$share"
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

test -f "$HOME/.local/share/mseries/stream/dictation-input.py" || { echo 'Install dictation input first (mseries/install-dictation-input.py).' >&2; exit 1; }
install -Dm0644 "$src/smart_reply_core.py" "$share/smart_reply_core.py"
install -Dm0755 "$src/smart-reply-input.py" "$share/smart-reply-input.py"
install -Dm0755 "$src/mseries-smart-reply" "$HOME/.local/bin/mseries-smart-reply"
install -Dm0644 "$src/mseries-smart-reply-input.service" "$units/mseries-smart-reply-input.service"
python3 - "$path" <<'PY'
import sys
from pathlib import Path
from gi.repository import Gio
MEDIA = "org.gnome.settings-daemon.plugins.media-keys"
custom = Gio.Settings.new_with_path(MEDIA + ".custom-keybinding", sys.argv[1])
for key, value in (("name", "Smart Reply"), ("command", str(Path.home() / ".local/bin/mseries-smart-reply")),
                   ("binding", "<Control><Alt>r")):
    custom.set_string(key, value)
s = Gio.Settings.new(MEDIA)
existing = s.get_strv("custom-keybindings")
if sys.argv[1] not in existing:
    s.set_strv("custom-keybindings", existing + [sys.argv[1]])
Gio.Settings.sync()
PY
systemctl --user daemon-reload
systemctl --user enable --now mseries-smart-reply-input.service
python3 "$HOME/.local/bin/mseries-smart-reply" --dry-run >/dev/null 2>&1 || true   # writes the default rules on first run
echo 'Installed Smart Reply. Click into a chat reply box and press Ctrl+Alt+R. Tab inserts, Esc discards.'
echo 'Rules: ~/.config/mseries/smart-reply.json (allow list of chat apps; edit to add or block apps and contacts).'
