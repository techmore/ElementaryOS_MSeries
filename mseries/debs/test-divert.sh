#!/usr/bin/env bash
# Prove that an M-series plugin package survives an upgrade of the stock
# package it replaces, and that removing it puts the stock plugin back.
#
#   bash mseries/debs/test-divert.sh PACKAGE.deb STOCK-PACKAGE MARKER
#
# Installs and removes packages with sudo, so it only runs in CI (it refuses
# without CI=true): never point it at the owner's desktop. A stock "upgrade" is
# simulated with `apt-get install --reinstall`, which writes the stock plugin
# exactly as a version upgrade would.
set -euo pipefail
deb=$(realpath "${1:?usage: test-divert.sh PACKAGE.deb STOCK-PACKAGE MARKER}")
stock_pkg=${2:?stock package}
marker=${3:?marker string in our plugin}
[[ ${CI:-} == true ]] || { echo "test-divert.sh modifies system packages; it runs only in CI" >&2; exit 2; }

pkg=$(dpkg-deb -f "$deb" Package)
plugin=/$(dpkg-deb -c "$deb" | awk '$6 ~ /wingpanel-9\/[^/]+\.so$/ {sub("^\\./", "", $6); print $6}')
[[ $plugin == /usr/lib/*/wingpanel-9/*.so ]] || { echo "$pkg: no wingpanel-9 plugin in package" >&2; exit 1; }
sum() { md5sum "$1" | cut -d' ' -f1; }
fail() { echo "FAIL $pkg: $*" >&2; exit 1; }

stock=$(sum "$plugin")
grep -aqF "$marker" "$plugin" && fail "stock plugin already contains '$marker'"

sudo dpkg -i "$deb" >/dev/null
ours=$(sum "$plugin")
[[ $ours != "$stock" ]] || fail "install left the stock plugin in place"
grep -aqF "$marker" "$plugin" || fail "installed plugin lacks '$marker'"
dpkg-divert --list "$plugin" | grep -qF "by $pkg" || fail "no diversion owned by $pkg"
[[ $(sum "$plugin.mseries-orig") == "$stock" ]] || fail "stock plugin was not moved aside intact"
echo "ok   $pkg: installed, stock plugin diverted to $plugin.mseries-orig"

sudo apt-get install --reinstall -y "$stock_pkg" >/dev/null
[[ $(sum "$plugin") == "$ours" ]] || fail "reinstalling $stock_pkg overwrote our plugin"
[[ $(sum "$plugin.mseries-orig") == "$stock" ]] || fail "reinstalled stock plugin did not land in the diverted path"
echo "ok   $pkg: survived a reinstall of $stock_pkg"

files=$(dpkg-deb -c "$deb" | awk '$1 !~ /^d/ {sub("^\\./", "/", $6); print $6}')
sudo dpkg -r "$pkg" >/dev/null
[[ $(sum "$plugin") == "$stock" ]] || fail "removal did not restore the stock plugin"
dpkg-divert --list "$plugin" | grep -q . && fail "diversion left behind after removal"
[[ ! -e $plugin.mseries-orig ]] || fail "diverted copy left behind after removal"
while read -r file; do
  [[ $file == "$plugin" || ! -e $file ]] || fail "$file left behind after removal"
done <<< "$files"
echo "ok   $pkg: removal restored the stock plugin and removed the diversion"
