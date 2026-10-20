#!/usr/bin/env bash
# Builds the Quick Settings TextScale widget with a driver and checks its ladder
# behaviour on a private display, session bus and in-memory GSettings backend.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
repo=$(cd -- "$here/../../.." && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
valac --pkg gtk4 --pkg granite-7 -X -lm -X -w -X -DGETTEXT_PACKAGE=\"mseries\" -d "$work" -o "$work/test-text-scale" \
    "$repo/mseries/quick-settings/TextScale.vala" "$here/test-text-scale.vala"
GSETTINGS_BACKEND=memory GDK_BACKEND=x11 XDG_CONFIG_HOME="$work" \
    xvfb-run -a dbus-run-session -- "$work/test-text-scale"
