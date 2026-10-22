#!/bin/bash
# Build and install Claude for elementary OS (rust/claude-pantheon-rs), the native T3 Code client.
#
#   bash mseries/install-claude-pantheon-rs.sh                # for this user, under ~/.local
#   bash mseries/install-claude-pantheon-rs.sh --prefix /usr  # system-wide
#   bash mseries/install-claude-pantheon-rs.sh --uninstall
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
crate="$repo/rust/claude-pantheon-rs"

if [[ ${1:-} != --uninstall && ${1:-} != --no-build ]]; then
    for tool in cargo rsvg-convert; do
        command -v "$tool" >/dev/null || {
            echo "Missing $tool. Install build requirements with:" >&2
            echo '  sudo apt install cargo libgtk-4-dev libgranite-7-dev librsvg2-bin' >&2
            exit 1
        }
    done
fi
exec bash "$crate/install.sh" "$@"
