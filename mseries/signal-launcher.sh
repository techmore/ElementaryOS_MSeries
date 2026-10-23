#!/usr/bin/env bash
# Apply the current elementary accent before opening the official Signal client.
set -euo pipefail

home=${HOME:?}
mode_file="$home/.local/state/mseries-signal/deployment-mode"
if [[ -f $mode_file && $(<"$mode_file") == atomic ]]; then
  exec /usr/bin/python3 "$home/.local/libexec/mseries-atomic-app" \
    --app signal-desktop-beta run -- --use-tray-icon "$@"
fi

appdir=${MSERIES_SIGNAL_APPDIR:-"$home/.local/lib/signal-desktop-beta"}
app="$appdir/AppRun"
accent_script="$home/.local/libexec/mseries-signal-accent.py"
if [[ ! -x $app ]]; then
  echo 'Signal is not installed. Run mseries/install-signal.sh first.' >&2
  exit 1
fi

# A theme refresh failure must not prevent access to the user's existing Signal
# account. The last working bundle remains launchable and the error is visible.
if ! /usr/bin/python3 "$accent_script" --sync --appdir "$appdir"; then
  if command -v notify-send >/dev/null; then
    notify-send --app-name='Signal' 'System accent not applied' \
      'Signal is opening with its last saved colors. Check the Signal integration install.' || true
  fi
fi

exec "$app" --use-tray-icon "$@"
