#!/usr/bin/env bash
# Install dev-clean for the current user with its weekly timer.
#   install.sh              install ~/.local/bin/dev-clean, the timer, and point ~/bin/dev-clean at it
#   install.sh --uninstall  remove the timer and the installed script (~/bin/dev-clean is restored only if it was a symlink)
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bin=$HOME/.local/bin/dev-clean
unit_dir=$HOME/.config/systemd/user

if [[ ${1:-} == --uninstall ]]; then
  systemctl --user disable --now dev-clean.timer 2>/dev/null || true
  rm -f "$bin" "$unit_dir/dev-clean.service" "$unit_dir/dev-clean.timer"
  [[ -L $HOME/bin/dev-clean ]] && rm -f "$HOME/bin/dev-clean"
  systemctl --user daemon-reload
  echo 'Removed dev-clean and its timer.'
  exit 0
fi

install -Dm0755 "$here/dev-clean.sh" "$bin"
mkdir -p "$HOME/.cache/dev-clean"
# The old hand-copied script at ~/bin/dev-clean becomes a link, so the habit keeps working and
# the repo copy is the only one.
if [[ -e $HOME/bin/dev-clean && ! -L $HOME/bin/dev-clean ]]; then
  mv "$HOME/bin/dev-clean" "$HOME/.cache/dev-clean/dev-clean.before-install"
fi
mkdir -p "$HOME/bin"
ln -sfn "$bin" "$HOME/bin/dev-clean"
install -Dm0644 "$here/dev-clean.service" "$unit_dir/dev-clean.service"
install -Dm0644 "$here/dev-clean.timer" "$unit_dir/dev-clean.timer"
systemctl --user daemon-reload
systemctl --user enable --now dev-clean.timer
systemctl --user list-timers dev-clean.timer --no-pager | head -2
echo "Installed: $bin (weekly timer; log in ~/.cache/dev-clean/last.log; dev-clean --dry-run previews)."
