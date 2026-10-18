#!/usr/bin/env bash
# Local dictation on the Mac's F5 (microphone) key, typed into any app.
# Voxtype (MIT, peteonrails/voxtype) + Whisper, ydotool for typing, as Omarchy does.
#   --uninstall   remove the binary, key remap and user service (keeps your config and models)
set -euo pipefail
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/dictation
version=1.1.1
asset=voxtype-$version-linux-aarch64-cpu
sha256=f29bdbf6c3c2535ebe8be3abb6ded7d6c0ac9b16392ea3b5ba231e06a7b05687
url=https://github.com/peteonrails/voxtype/releases/download/v$version/$asset
[[ $EUID != 0 ]] || { echo 'Run as your normal user; sudo is used where needed.' >&2; exit 2; }

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now voxtype.service 2>/dev/null || true
  rm -f ~/.config/systemd/user/voxtype.service
  systemctl --user disable --now mseries-aop-mic.service 2>/dev/null || true
  rm -f ~/.config/systemd/user/mseries-aop-mic.service
  sudo rm -rf /usr/local/libexec/mseries/aop-mic.sh
  sudo rm -f /usr/local/bin/voxtype /etc/udev/hwdb.d/91-mseries-dictation.hwdb
  sudo systemd-hwdb update && sudo udevadm trigger --subsystem-match=input --action=change
  exit 0
fi

dpkg -s ydotool wl-clipboard >/dev/null 2>&1 || sudo apt-get install -y ydotool wl-clipboard
# ydotool types through /dev/uinput (group input). Make sure we are in it.
id -nG | tr ' ' '\n' | grep -qx input || { sudo usermod -aG input "$USER"; echo 'Added you to group input: log out and in once.'; }

work=$(mktemp -d); trap 'rm -rf "$work"' EXIT
if [[ ! -x /usr/local/bin/voxtype ]] || ! echo "$sha256  /usr/local/bin/voxtype" | sha256sum -c --quiet 2>/dev/null; then
  curl -fL --proto '=https' -o "$work/$asset" "$url"
  echo "$sha256  $work/$asset" | sha256sum -c --quiet
  sudo install -m 755 "$work/$asset" /usr/local/bin/voxtype
fi

# F5 -> KEY_F20 (the hid-apple backlight translation then no longer fires on F5).
sudo install -Dm644 "$here/91-mseries-dictation.hwdb" /etc/udev/hwdb.d/91-mseries-dictation.hwdb
sudo systemd-hwdb update
sudo udevadm trigger --subsystem-match=input --action=change

mkdir -p ~/.config/voxtype ~/.config/systemd/user
[[ -e ~/.config/voxtype/config.toml ]] || install -m644 "$here/config.toml" ~/.config/voxtype/config.toml
sudo install -Dm755 "$here/aop-mic.sh" /usr/local/libexec/mseries/aop-mic.sh
install -m644 "$here/mseries-aop-mic.service" ~/.config/systemd/user/mseries-aop-mic.service
install -m644 "$here/voxtype.service" ~/.config/systemd/user/voxtype.service
/usr/local/bin/voxtype setup --download --no-post-install   # fetches the configured Whisper model if missing

systemctl --user daemon-reload
systemctl --user enable --now ydotool.service mseries-aop-mic.service voxtype.service
echo 'Dictation ready: hold F5, speak, release.'
