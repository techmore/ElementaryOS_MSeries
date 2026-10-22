#!/bin/bash
# Build and install the Claude Wingpanel indicator (rust/claude-pantheon-rs/wingpanel-indicator):
# pending permission prompts, running threads and the plan window nearest exhaustion, on the panel.
#
#   bash mseries/install-claude-pantheon-indicator.sh
#   bash mseries/install-claude-pantheon-indicator.sh --uninstall
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if [[ ${1:-} != --uninstall ]]; then
    source "$repo/mseries/lib-apt.sh"
    mseries_apt_refresh
    sudo apt-get install -y meson ninja-build valac pkg-config libwingpanel-dev libgranite-7-dev libjson-glib-dev libgee-0.8-dev
fi
exec bash "$repo/rust/claude-pantheon-rs/wingpanel-indicator/install.sh" "$@"
