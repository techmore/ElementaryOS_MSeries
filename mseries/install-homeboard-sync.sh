#!/usr/bin/env bash
# Install the Homeboard ↔ elementary Tasks bridge for this user, without the separate
# Homeboard indicator: the calendar dropdown's Tasks tab shows the Homeboard list and
# its sync status (see mseries/calendar/README.md).
#
# Source: techmore/homeboard (private; needs the owner's GitHub access) at the pinned
# commit below, or HOMEBOARD_SOURCE=/path/to/checkout for a reviewed local checkout.
# Google sign-in is the owner's step: choose Sign In… in the Tasks tab afterwards.
set -euo pipefail
repository=https://github.com/techmore/homeboard.git
commit=${HOMEBOARD_COMMIT:-6d91c42344abe3ca04299ea0e884d286d6db05ad}

if [[ ${1:-} == --uninstall ]]; then
    rm -f "$HOME/.config/autostart/homeboard.desktop" \
          "$HOME/.local/share/applications/org.techmore.Homeboard.desktop"
    rm -rf "$HOME/.local/lib/homeboard"
    echo 'Removed the Homeboard bridge. Its Tasks list, sync state and keyring entry are kept.'
    exit
fi

python3 - <<'PY'
import gi
for name, version in [('Gtk', '4.0'), ('ECal', '2.0'), ('EDataServer', '1.2'), ('Secret', '1'), ('ICalGLib', '3.0')]:
    gi.require_version(name, version)
PY

if [[ -n ${HOMEBOARD_SOURCE:-} ]]; then
    source=$(cd -- "$HOMEBOARD_SOURCE" && pwd)
else
    work=$(mktemp -d "${TMPDIR:-/tmp}/mseries-homeboard.XXXXXX")
    trap 'rm -rf "$work"' EXIT
    git init -q "$work/source"
    git -C "$work/source" remote add origin "$repository"
    # Private repository: use the GitHub CLI's sign-in when git has no credentials of its own.
    auth=()
    command -v gh >/dev/null && auth=(-c credential.helper= -c 'credential.helper=!gh auth git-credential')
    git "${auth[@]}" -C "$work/source" fetch -q --depth=1 origin "$commit"
    git -C "$work/source" checkout -q --detach FETCH_HEAD
    source=$work/source
fi

# The calendar's Sync and Sign In buttons need the bridge's background mode and D-Bus actions.
if ! grep -q -- "--background" "$source/linux/desktop.py" || ! grep -q -- "--no-indicator" "$source/linux/install.sh"; then
    echo "This Homeboard revision predates background sync and D-Bus actions; nothing installed." >&2
    echo "Pin a newer techmore/homeboard commit (HOMEBOARD_COMMIT) or use HOMEBOARD_SOURCE." >&2
    exit 1
fi

bash "$source/linux/install.sh" --no-indicator
# The bridge's app opens the board too, so the older browser-only launcher is redundant.
rm -f "$HOME/.local/share/applications/org.techmore.HomeboardBoard.desktop"
# Start it now in the background; at the next login, autostart does this.
if ! gdbus call --session --dest org.freedesktop.DBus --object-path /org/freedesktop/DBus \
        --method org.freedesktop.DBus.NameHasOwner org.techmore.Homeboard 2>/dev/null | grep -q true; then
    setsid /usr/bin/python3 "$HOME/.local/lib/homeboard/desktop.py" --background >/dev/null 2>&1 < /dev/null &
fi
echo 'Installed the Homeboard bridge. Open the calendar → Tasks and choose Sign In… to connect Google.'
