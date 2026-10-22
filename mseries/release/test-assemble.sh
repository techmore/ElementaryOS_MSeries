#!/usr/bin/env bash
# Offline test of assemble-apt.sh and the channel version rules, with a throwaway key and fake debs.
# Needs apt-utils (apt-ftparchive), gnupg and dpkg-dev; nothing is installed or published.
#   bash mseries/release/test-assemble.sh
set -euo pipefail

HERE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ASSEMBLE=$HERE/assemble-apt.sh
WORK=$(mktemp -d "${TMPDIR:-/tmp}/mseries-assemble-test.XXXXXX")
trap 'gpgconf --kill gpg-agent >/dev/null 2>&1 || true; rm -rf "$WORK"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }
ok() { echo "ok: $*"; }

# --- throwaway key: primary kept apart, signing subkey only in the "secret" ---------------
export GNUPGHOME=$WORK/gnupg
mkdir -m 0700 "$GNUPGHOME"
gpg --batch --quiet --passphrase '' --quick-gen-key 'M-series test <test@invalid>' ed25519 cert never
primary=$(gpg --batch --list-keys --with-colons | awk -F: '$1 == "fpr" { print $10; exit }')
gpg --batch --quiet --passphrase '' --quick-add-key "$primary" ed25519 sign 1y
MSERIES_APT_KEY=$(gpg --batch --armor --export-secret-subkeys "$primary")
export MSERIES_APT_KEY
rm -rf "$GNUPGHOME"   # assemble-apt.sh must work from the exported secret alone

mkdeb() { # mkdeb DIR NAME VERSION
  local root=$WORK/pkg-$2-$3
  mkdir -p "$root/DEBIAN" "$root/usr/share/$2"
  printf 'x' > "$root/usr/share/$2/file"
  printf 'Package: %s\nVersion: %s\nArchitecture: arm64\nMaintainer: t <t@invalid>\nDescription: test\n' "$2" "$3" > "$root/DEBIAN/control"
  mkdir -p "$1"
  dpkg-deb --build --root-owner-group "$root" "$1/$2_${3}_arm64.deb" >/dev/null
}

tree=$WORK/apt
stable_in=$WORK/in-stable
dev_in=$WORK/in-dev
mkdeb "$stable_in" mseries-update 0.1.0-0mseries3
mkdeb "$stable_in" mseries-quick-settings 1.4.0-0mseries3

# --- 1. fails closed: no key means no output at all ---------------------------------------
if env -u MSERIES_APT_KEY bash "$ASSEMBLE" --channel stable --incoming "$stable_in" --tree "$tree" 2>"$WORK/err"; then
  fail "published without MSERIES_APT_KEY"
fi
grep -q 'MSERIES_APT_KEY is not set' "$WORK/err" || fail "missing-key message not shown"
[[ ! -e $tree ]] || fail "tree was written without a key"
ok "no key: refuses, writes nothing"
if MSERIES_APT_KEY='not a key' bash "$ASSEMBLE" --channel stable --incoming "$stable_in" --tree "$tree" 2>/dev/null; then
  fail "accepted a garbage key"
fi
[[ ! -e $tree/dists ]] || fail "garbage key left a dists tree"
ok "garbage key: refuses"

# --- 2. stable, then dev: both suites live, neither disturbs the other --------------------
bash "$ASSEMBLE" --channel stable --incoming "$stable_in" --tree "$tree" >/dev/null
stable_before=$(cd "$tree" && find dists/stable pool/stable -type f -exec sha256sum {} + | sort)
mkdeb "$dev_in" mseries-update 0.1.0-0mseries3~dev20261021153012.abc1234
bash "$ASSEMBLE" --channel dev --incoming "$dev_in" --tree "$tree" >/dev/null
stable_after=$(cd "$tree" && find dists/stable pool/stable -type f -exec sha256sum {} + | sort)
[[ $stable_before == "$stable_after" ]] || fail "publishing dev changed the stable suite"
for f in InRelease Release Release.gpg main/binary-arm64/Packages main/binary-arm64/Packages.gz; do
  [[ -s $tree/dists/stable/$f && -s $tree/dists/dev/$f ]] || fail "missing $f in a suite"
done
grep -q '^Suite: dev$' "$tree/dists/dev/Release" && grep -q '^Suite: stable$' "$tree/dists/stable/Release" \
  || fail "Suite fields wrong"
ok "stable and dev coexist; dev publish leaves stable byte-identical"

# --- 3. signatures verify, and tampering is caught ----------------------------------------
gpgv --keyring "$tree/mseries-archive-keyring.gpg" "$tree/dists/dev/InRelease" 2>/dev/null || fail "InRelease"
cp "$tree/dists/stable/InRelease" "$WORK/tampered"
sed -i 's/^Suite: stable/Suite: stablx/' "$WORK/tampered"
if gpgv --keyring "$tree/mseries-archive-keyring.gpg" "$WORK/tampered" 2>/dev/null; then fail "tampered InRelease verified"; fi
ok "InRelease/Release.gpg verify; a modified InRelease does not"

# --- 4. real apt accepts both suites with only our keyring --------------------------------
if command -v apt-get >/dev/null; then
  for suite in stable dev; do
    a=$WORK/apt-$suite
    mkdir -p "$a/state/lists/partial" "$a/cache/archives/partial" "$a/etc"
    : > "$a/status"
    printf 'deb [signed-by=%s arch=arm64] file:%s %s main\n' "$tree/mseries-archive-keyring.gpg" "$tree" "$suite" > "$a/etc/sources.list"
    apt-get -q -o Dir::Etc::sourcelist="$a/etc/sources.list" -o Dir::Etc::sourceparts=/dev/null \
      -o Dir::State="$a/state" -o Dir::State::status="$a/status" -o Dir::Cache="$a/cache" \
      -o APT::Architecture=arm64 -o APT::Architectures::=arm64 -o Debug::NoLocking=1 -o APT::Sandbox::User=root update >"$a/log" 2>&1 \
      || { cat "$a/log" >&2; fail "apt-get update rejected the $suite suite"; }
    ! grep -Eq '^(W|E):' "$a/log" || { cat "$a/log" >&2; fail "apt warned about the $suite suite"; }
    apt-cache -o Dir::Etc::sourcelist="$a/etc/sources.list" -o Dir::Etc::sourceparts=/dev/null \
      -o Dir::State="$a/state" -o Dir::State::status="$a/status" -o Dir::Cache="$a/cache" \
      -o APT::Architecture=arm64 -o APT::Architectures::=arm64 policy mseries-update | grep -q 'Candidate: 0.1.0-0mseries3' \
      || fail "$suite does not offer mseries-update"
  done
  ok "apt-get update + policy accept both signed suites without warnings"
else
  echo "skip: apt-get not available" >&2
fi

# --- 5. dev retention and the version order the updater relies on -------------------------
for i in 1 2 3 4 5 6; do
  mkdeb "$dev_in" mseries-update "0.1.0-0mseries3~dev2026102215000$i.abc123$i"
done
KEEP=3 bash "$ASSEMBLE" --channel dev --incoming "$dev_in" --tree "$tree" | grep -c '^prune ' | grep -qx 4 \
  || fail "expected 4 pruned dev versions (7 -> 3)"
mapfile -t left < <(cd "$tree/pool/dev" && ls)
(( ${#left[@]} == 3 )) || fail "dev pool should hold 3 files, has ${#left[@]}"
[[ ${left[*]} == *'~dev202610221500'*6* ]] || fail "newest dev version was pruned"
(cd "$tree/pool/stable" && ls | wc -l | grep -qx 2) || fail "stable was pruned"
ok "dev keeps the newest N by dpkg order; stable keeps everything"

dpkg --compare-versions '1.4.0-0mseries3' gt '1.4.0-0mseries3~dev20261021235959.fffffff' || fail "stable must sort above its dev builds"
dpkg --compare-versions '1.4.0-0mseries3~dev20261022000000.0000000' gt '1.4.0-0mseries3~dev20261021235959.fffffff' || fail "later dev must sort above earlier dev regardless of sha"
dpkg --compare-versions '1.4.0-0mseries4~dev20260101000000.0000000' gt '1.4.0-0mseries3' || fail "next revision's dev build must sort above the previous stable"
ok "version ordering: dev < same-revision stable; dev orders by commit time, not sha"
echo "all assemble-apt tests passed"
