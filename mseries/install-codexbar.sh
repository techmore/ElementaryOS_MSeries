#!/bin/bash
# Install upstream Linux ARM64 desktop + CLI; no fork required.
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
version=v0.77.0
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
mkdir -p "$HOME/.local/lib/codexbar-cli" "$HOME/.local/bin"
install -m 0755 "$repo/mseries/codexbar-opencode-local.py" "$HOME/.local/lib/codexbar-cli/codexbar-opencode-local.py"
install -m 0644 "$repo/mseries/codexbar_cache.py" "$HOME/.local/lib/codexbar-cli/codexbar_cache.py"
install -m 0755 "$repo/mseries/codexbar-sessions.py" "$HOME/.local/lib/codexbar-cli/codexbar-sessions.py"
install -m 0755 "$repo/mseries/codexbar-accounts.py" "$HOME/.local/lib/codexbar-cli/codexbar-accounts.py"
install -m 0755 "$repo/mseries/codexbar-claude.py" "$HOME/.local/lib/codexbar-cli/codexbar-claude.py"
install -m 0755 "$repo/mseries/codexbar-opencode-login.py" "$HOME/.local/lib/codexbar-cli/codexbar-opencode-login.py"
tar -xzf "CodexBarCLI-${version}-linux-aarch64.tar.gz" -C "$HOME/.local/lib/codexbar-cli"
mv -f "$HOME/.local/lib/codexbar-cli/codexbar" "$HOME/.local/lib/codexbar-cli/codexbar-upstream"
# Replace atomically so the panel never finds ~/.local/bin/codexbar missing mid-install.
install -m 0755 "$repo/mseries/codexbar-opencode-wrapper.py" "$HOME/.local/bin/codexbar.new"
mv -f "$HOME/.local/bin/codexbar.new" "$HOME/.local/bin/codexbar"
tar -xzf "CodexBarDesktop-${version}-linux-aarch64.tar.gz"
cd "CodexBarDesktop-${version}-linux-aarch64"
python3 Integrations/Linux/install.py --cli "$HOME/.local/bin/codexbar"
config_dir="${XDG_CONFIG_HOME:-$HOME/.config}/codexbar"
config_file="$config_dir/linux.json"
python3 - "$config_file" <<'PY'
import json
import os
import pathlib
import sys
import tempfile

path = pathlib.Path(sys.argv[1])
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
    config["providerOrder"] = list(dict.fromkeys([*order, "opencodego"]))
    config["provider"] = "custom"
else:
    print(f"Preserved CodexBar provider selection '{provider}'; add OpenCode Go in Settings → Providers.")

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
echo 'Open ~/.local/bin/codexbar-linux --settings. Runtime dependencies: see mseries/DESKTOP-SETUP.md.'
