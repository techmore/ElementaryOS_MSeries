#!/bin/bash
# Install the patched Pantheon Files: Created column, Date Created sort, newest-first default
# sort and a preview pane beside the list view (mseries/patches/files-created-column-preview.patch).
#
#   bash mseries/install-files-created-column.sh             build and install (asks for sudo itself)
#   bash mseries/install-files-created-column.sh --uninstall  remove the pin and go back to the archive build
#
# The debs carry epoch 1 and an apt pin keeps them, so `apt upgrade` does not revert this.
# Restart Files (or log out and in) to load it; running Files windows are left alone.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
pin=/etc/apt/preferences.d/mseries-pantheon-files

if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f "$pin"
  sudo apt-get install -y --allow-downgrades pantheon-files/resolute libpantheon-files-core0/resolute
  echo 'Back on the archive Pantheon Files. Restart Files.'
  exit 0
fi

version=$(dpkg-query -W -f='${Version}' pantheon-files 2>/dev/null || true)
case $version in
  7.3.3+r6841*|1:7.3.3+r6841*) ;;
  *) echo "This patch targets pantheon-files 7.3.3+r6841; found ${version:-none}. Rebase the patch first." >&2; exit 1 ;;
esac
for tool in git meson ninja valac dpkg-deb; do
  command -v "$tool" >/dev/null || { echo "Missing $tool (see mseries/install-files-portal-fix.sh for the build requirements)." >&2; exit 1; }
done

out=$(mktemp -d "${TMPDIR:-/tmp}/files-debs.XXXXXX")
trap 'rm -rf "$out"' EXIT
OUTDIR=$out bash "$repo/mseries/debs/build-files.sh"
new=$(cat "$out/VERSION")
if dpkg --compare-versions "$version" gt "$new"; then
  echo "Installed $version is newer than $new; nothing to do." >&2; exit 1
fi

printf 'Package: pantheon-files libpantheon-files-core0\nPin: version 1:*\nPin-Priority: 1001\n' | sudo tee "$pin" >/dev/null
sudo apt-get install -y --allow-downgrades "$out"/*.deb
echo "Installed Pantheon Files $new. Restart Files to use it."
