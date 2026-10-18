#!/bin/bash
# Install the optional elementary OS GitHub repository status indicator.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
indicators_dir=$(pkg-config --variable=indicatorsdir wingpanel-9 2>/dev/null || true)

if [[ ${1:-} == --uninstall ]]; then
  [[ -n $indicators_dir ]] && sudo rm -f "$indicators_dir/librepobar.so"
  rm -f "$HOME/.local/bin/mseries-repobar" "$HOME/.local/lib/mseries/repobar.py"
  echo 'Removed the RepoBar Wingpanel indicator and per-user helper. Cached GitHub status remains in ~/.cache/mseries/repobar/snapshot.json.'
  exit 0
fi

mseries_apt_refresh
sudo apt-get install -y gh meson ninja-build valac pkg-config \
  libwingpanel-9-dev libgranite-7-dev libjson-glib-dev

for tool in gh meson ninja valac pkg-config; do
  command -v "$tool" >/dev/null || {
    echo "Missing $tool; install the packages listed above and retry." >&2
    exit 1
  }
done

install -d -m 0755 "$HOME/.local/lib/mseries" "$HOME/.local/bin"
install -m 0644 "$repo/mseries/repobar.py" "$HOME/.local/lib/mseries/repobar.py"
printf '#!/bin/sh\nexec /usr/bin/python3 "%s" "$@"\n' \
  "$HOME/.local/lib/mseries/repobar.py" > "$HOME/.local/bin/mseries-repobar.new"
chmod 0755 "$HOME/.local/bin/mseries-repobar.new"
mv -f "$HOME/.local/bin/mseries-repobar.new" "$HOME/.local/bin/mseries-repobar"

build_dir=$(mktemp -d "${TMPDIR:-/tmp}/mseries-repobar.XXXXXX")
trap 'rm -rf "$build_dir"' EXIT
meson setup "$build_dir" "$repo/mseries/repobar-wingpanel" --prefix=/usr
ninja -C "$build_dir"
sudo ninja -C "$build_dir" install

echo 'RepoBar is installed in Wingpanel. Authenticate once with `gh auth login`, then reopen the menu.'
echo 'The indicator only reads GitHub data and keeps a private, 5-minute local cache.'
