#!/usr/bin/env bash
# Install, upgrade or remove the Homeboard ↔ elementary Tasks bridge for this user,
# without the separate Homeboard indicator: the calendar dropdown's Tasks tab shows the
# Homeboard list and its sync status (see mseries/calendar/README.md).
#   bash mseries/install-homeboard-sync.sh [--uninstall]
#
# Source: techmore/homeboard (private; needs the owner's GitHub access) at the pinned
# commit below, or HOMEBOARD_SOURCE=/path/to/checkout for a reviewed local checkout.
# The bridge's own installer starts it, replaces a running older revision, adds login
# autostart and D-Bus activation. Google sign-in is the owner's step: choose Sign In…
# in the calendar's Tasks tab afterwards.
set -euo pipefail
repository=https://github.com/techmore/homeboard.git
commit=${HOMEBOARD_COMMIT:-eae570cffd47c5c61415ad32fb48154a48822d39}
case ${1:-} in
    ''|--uninstall) ;;
    *) echo 'Usage: install-homeboard-sync.sh [--uninstall]' >&2; exit 2 ;;
esac

if [[ -n ${HOMEBOARD_SOURCE:-} ]]; then
    source=$(cd -- "$HOMEBOARD_SOURCE" && pwd)
    version=$(git -C "$source" rev-parse HEAD 2>/dev/null || echo local)
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
    version=$commit
fi

# The calendar's buttons need background mode, D-Bus actions and installer lifecycle support.
if ! grep -q -- "--uninstall" "$source/linux/install.sh" || ! grep -q "'quit'" "$source/linux/desktop.py"; then
    echo "This Homeboard revision predates the production bridge; nothing changed." >&2
    echo "Pin a newer techmore/homeboard commit (HOMEBOARD_COMMIT) or use HOMEBOARD_SOURCE." >&2
    exit 1
fi

if [[ ${1:-} == --uninstall ]]; then
    bash "$source/linux/install.sh" --uninstall
    exit
fi
HOMEBOARD_VERSION=$version bash "$source/linux/install.sh" --no-indicator
# The bridge's app opens the board too, so the older browser-only launcher is redundant.
rm -f "$HOME/.local/share/applications/org.techmore.HomeboardBoard.desktop"
echo 'Open the calendar → Tasks and choose Sign In… to connect Google, if not signed in yet.'
