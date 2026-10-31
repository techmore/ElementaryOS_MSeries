#!/bin/bash
# Install upstream Linux ARM64 desktop + CLI; no fork required.
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
version=v0.83.0
if [[ ${1:-} != --skip-system-deps ]]; then
  mseries_apt_refresh
  sudo apt-get install -y \
    qml6-module-qtquick qml6-module-qtquick-controls \
    qml6-module-qtquick-layouts qml6-module-qtquick-templates \
    qml6-module-qtquick-window qml6-module-qtqml-workerscript \
    libqt6widgets6 libqt6svg6 qt6-wayland xdg-terminal-exec
fi
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cd "$work"
for component in CLI Desktop; do
  archive="CodexBar${component}-${version}-linux-aarch64.tar.gz"
  base="https://github.com/steipete/CodexBar/releases/download/${version}"
  curl -fLsS "$base/$archive" -o "$archive"
  curl -fLsS "$base/$archive.sha256" -o "$archive.sha256"
  sha256sum -c "$archive.sha256"
done
source "$repo/mseries/lib-codexbar.sh"
codexbar_install_helpers "$repo"
tar -xzf "CodexBarCLI-${version}-linux-aarch64.tar.gz" -C "$HOME/.local/lib/codexbar-cli"
mv -f "$HOME/.local/lib/codexbar-cli/codexbar" "$HOME/.local/lib/codexbar-cli/codexbar-upstream"
# v0.78.0's CLI linked libxml2.so.2 and needed a wrapper on this base; v0.79.0+ does not, and the shim removes itself.
codexbar_install_cli_compat
codexbar_install_wrapper "$repo"
tar -xzf "CodexBarDesktop-${version}-linux-aarch64.tar.gz"
cd "CodexBarDesktop-${version}-linux-aarch64"
python3 Integrations/Linux/install.py --cli "$HOME/.local/bin/codexbar"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/codexbar"
config_file="$config_dir/linux.json"
# Grok Build joins the panel only when its CLI is installed; upstream reads ~/.grok/auth.json and `grok agent stdio`.
grok_installed=0
if command -v grok >/dev/null || [[ -x "${GROK_HOME:-$HOME/.grok}/bin/grok" || -x "$HOME/.local/bin/grok" ]]; then
  grok_installed=1
fi
python3 - "$config_file" "$grok_installed" <<'PY'
import json
import os
import pathlib
import sys
import tempfile

path = pathlib.Path(sys.argv[1])
grok_installed = sys.argv[2] == "1"
path.parent.mkdir(parents=True, exist_ok=True)
config = {}
if path.exists():
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Cannot update CodexBar settings at {path}: {error}")
    if not isinstance(config, dict):
        raise SystemExit(f"Cannot update CodexBar settings at {path}: expected a JSON object")

provider = config.get("provider", "codex")
if not isinstance(provider, str):
    raise SystemExit(f"Cannot update CodexBar settings at {path}: invalid provider")
if provider in {"codex", "both", "custom"}:
    order = config.get("providerOrder", [])
    if not isinstance(order, list) or not all(isinstance(item, str) for item in order):
        raise SystemExit(f"Cannot update CodexBar settings at {path}: invalid providerOrder")
    if provider == "codex":
        order = ["codex", *[item for item in order if item != "codex"]]
    elif provider == "both":
        order = ["codex", "claude", *[item for item in order if item not in {"codex", "claude"}]]
    added = ["opencodego", *(["grok"] if grok_installed else [])]
    config["providerOrder"] = list(dict.fromkeys([*order, *added]))
    config["provider"] = "custom"
else:
    print(f"Preserved CodexBar provider selection '{provider}'; add OpenCode Go"
          f"{' and Grok' if grok_installed else ''} in Settings → Providers.")

if config.get("provider") == "custom":
    destination = path.resolve()
    descriptor, temporary_name = tempfile.mkstemp(prefix=destination.name + ".", dir=destination.parent)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as temporary:
            temporary.write(json.dumps(config, indent=2) + "\n")
        pathlib.Path(temporary_name).replace(destination)
    except BaseException:
        pathlib.Path(temporary_name).unlink(missing_ok=True)
        raise
PY
# Start CodexBar at login (idempotent; the Wingpanel indicator also launches it when the session loads it).
"$HOME/.local/bin/codexbar-linux" --autostart enable >/dev/null 2>&1 || echo 'Could not enable start at login; use Settings > Start at login.' >&2
echo 'Open ~/.local/bin/codexbar-linux --settings. Runtime dependencies: see mseries/DESKTOP-SETUP.md.'
