#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-backup.sh"
if [[ ${1:-} == --uninstall ]]; then
  mseries_restore /usr/bin/gala-daemon gala
  echo 'Restored original helper; log out and back in to activate.'
  exit
fi
version=$(dpkg-query -W -f='${Version}' gala)
[[ $version == 8.6.2* ]] || { echo "Patch targets Gala 8.6.2, found $version" >&2; exit 1; }
work=$(mktemp -d /tmp/mseries-gala-osk.XXXXXX)
trap 'rm -rf "$work"' EXIT
git init -q "$work/source"
git -C "$work/source" remote add origin https://github.com/elementary/gala.git
git -C "$work/source" fetch -q --depth=1 origin f0791434ac40a50f2aec64700a47b3bb04145752
git -C "$work/source" checkout -q --detach FETCH_HEAD
git -C "$work/source" apply "$repo/mseries/patches/gala-disabled-osk-input-purpose.patch"
/usr/bin/python3 "$repo/mseries/gala-daemon-fix/build.py" "$work/source" "$work/build"
if ldd "$work/build/gala-daemon" | grep -q 'not found'; then exit 1; fi
mseries_backup /usr/bin/gala-daemon gala
sudo install -m755 "$work/build/gala-daemon" /usr/bin/gala-daemon
echo 'Installed disabled-keyboard guard in the GTK helper; log out and back in to activate.'
