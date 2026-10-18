#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
case "${1:-}" in
  --dry-run) printf '%s\n' 'Install a user-owned copy, npm locked dependencies, user service and desktop launcher. No root, audio, boot or firewall changes.'; exit 0 ;;
  --uninstall)
    systemctl --user disable --now mseries-webrtc.service 2>/dev/null || true
    rm -f -- "$HOME/.config/systemd/user/mseries-webrtc.service" "$HOME/.local/share/applications/mseries-webrtc.desktop" "$HOME/.local/bin/mseries-webrtc-open" "$HOME/.local/bin/mseries-webrtc-check" "$HOME/.local/bin/mseries-webrtc-configure"
    rm -rf -- "$HOME/.local/share/mseries-webrtc"
    systemctl --user daemon-reload
    printf '%s\n' 'Removed. Owner key and deployment settings retained in ~/.config/mseries-webrtc; remove that directory to revoke the key.'
    exit 0 ;;
  '') ;;
  *) printf 'Usage: %s [--dry-run|--uninstall]\n' "$0" >&2; exit 2 ;;
esac
[[ $(uname -s) == Linux ]] || { echo 'Install on the ElementaryOS Linux desktop.' >&2; exit 1; }
[[ $EUID != 0 ]] || { echo 'Run as the desktop user, without sudo.' >&2; exit 1; }
node -e 'if (Number(process.versions.node.split(".")[0]) < 22) process.exit(1)' || { echo 'Node.js 22 or newer is required.' >&2; exit 1; }
/usr/bin/python3 -c 'from gi.repository import Gio, GLib' || { echo 'Install python3-gi for phone control.' >&2; exit 1; }
install_root="$HOME/.local/share/mseries-webrtc"
mkdir -p -- "$install_root/public" "$HOME/.config/systemd/user" "$HOME/.config/mseries-webrtc" "$HOME/.local/bin" "$HOME/.local/share/applications"
chmod 700 -- "$HOME/.config/mseries-webrtc"
install -m 644 server.mjs package.json package-lock.json input_bridge.py preflight.py setup_desktop.py "$install_root/"
install -m 644 public/* "$install_root/public/"
(cd -- "$install_root" && npm ci --omit=dev --ignore-scripts --no-audit --no-fund)
install -m 755 open.py "$HOME/.local/bin/mseries-webrtc-open"
install -m 755 preflight.py "$HOME/.local/bin/mseries-webrtc-check"
install -m 755 setup_desktop.py "$HOME/.local/bin/mseries-webrtc-configure"
# Quote an executable path for systemd (paths with spaces are supported).
node_path=$(command -v node)
python3 - "$install_root" "$node_path" <<'PY'
import json, pathlib, sys
root, node = sys.argv[1:]
unit = f'''[Unit]
Description=M-series WebRTC screen sharing
PartOf=graphical-session.target
After=graphical-session.target

[Service]
Type=simple
ExecStart={json.dumps(node)} {json.dumps(root + '/server.mjs')}
EnvironmentFile=-%h/.config/mseries-webrtc/environment
Restart=on-failure
RestartSec=3
UMask=0077
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=graphical-session.target
'''
pathlib.Path.home().joinpath('.config/systemd/user/mseries-webrtc.service').write_text(unit)
PY
cat > "$HOME/.local/share/applications/mseries-webrtc.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Screen Share
Comment=Share, record, or control your desktop from a phone
Exec="$HOME/.local/bin/mseries-webrtc-open"
Icon=video-display
Categories=Network;RemoteAccess;
Terminal=false
DESKTOP
systemctl --user daemon-reload
systemctl --user enable --now mseries-webrtc.service
printf '%s\n' 'Installed. Open Screen Share from the app launcher. Select a screen before connecting your phone.'
