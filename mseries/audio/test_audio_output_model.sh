#!/usr/bin/env bash
# Compiles quick-settings/AudioOutputModel.vala with a fixture test and runs it. No GTK, no audio
# changes: it only parses saved pw-dump output.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
valac --pkg json-glib-1.0 -X -DGETTEXT_PACKAGE=\"test\" -o "$work/test" "$here/../quick-settings/AudioOutputModel.vala" "$here/test_audio_output_model.vala" 2>&1 | grep -v -E 'warning|^ *[0-9]+ \||\^|^$' || true
"$work/test" "$here/fixtures"
