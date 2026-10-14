#!/usr/bin/env bash
set -euo pipefail

home=${HOME:?HOME must be set}
applications="$home/.local/share/applications"
mkdir -p "$applications"
cat > "$applications/org.techmore.HomeboardBoard.desktop" <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=Homeboard
Comment=Open the household project board
Exec=xdg-open https://tasks.stoverparc.org/board/
Icon=io.elementary.tasks
Terminal=false
Categories=Office;ProjectManagement;
DESKTOP
chmod 0644 "$applications/org.techmore.HomeboardBoard.desktop"
echo "Installed Homeboard launcher in $applications"
echo 'The board requires Google sign-in. The separate Tasks sync bridge needs Evolution Data Server packages.'
