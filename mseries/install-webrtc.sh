#!/usr/bin/env bash
# Installed-system entry point; factory images already contain the runtime.
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ ${1:-} == --dry-run || ${1:-} == --uninstall ]]; then
  exec bash "$here/webrtc/install.sh" "$@"
fi
if [[ -x /usr/bin/mseries-webrtc-open && -f /usr/lib/mseries-webrtc/server.mjs ]]; then
  echo 'Screen Share is built into this image. Open it from the app launcher.'
  exit 0
fi
command -v node >/dev/null && node -e 'if (Number(process.versions.node.split(".")[0]) < 22) process.exit(1)' && command -v npm >/dev/null && /usr/bin/python3 -c 'from gi.repository import Gio' 2>/dev/null || {
  sudo apt-get update
  sudo apt-get install -y nodejs npm python3-gi
}
exec bash "$here/webrtc/install.sh" "$@"
