#!/bin/bash
# Read-only private-framework export. macOS already includes JXA/Foundation.
set -euo pipefail
umask 077
[ "$(uname -s)" = Darwin ] || { echo 'Run this on your macOS partition.' >&2; exit 1; }
here=$(cd -- "$(dirname -- "$0")" && pwd)
destination=${1:-"$HOME/Downloads/MSeries-Message-Pins"}
mkdir -p "$destination"
target="$destination/apple-message-pins.json"
if [ -e "$target" ]; then
  cp -p "$target" "$destination/apple-message-pins-before-$(date -u +%Y%m%dT%H%M%SZ).json"
fi
printf '%s\n' 'Open Messages on this Mac and wait until its pinned conversations match your iPhone.'
printf '%s\n' 'This helper reads those pins through IMCore. It does not send messages or change pins.'
printf '%s\n' 'Keep this small private export on storage accessible from Linux, including your NAS if mounted.'
/usr/bin/osascript -l JavaScript "$here/Export-Message-Pins.js" --output "$target"
printf 'Saved private pin snapshot: %s\n' "$target"
printf '%s\n' 'On Linux: Messages → menu → Import iPhone Pins. Check the conversation matches before importing.'
