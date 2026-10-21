#!/usr/bin/env bash
# Add one channel's .debs to the static apt tree and re-sign only that suite.
#
#   bash mseries/release/assemble-apt.sh --channel dev --incoming out/mseries-debs --tree gh-pages-checkout/apt
#
# The tree holds both suites side by side: pool/<suite>/*.deb and dists/<suite>/. Publishing
# one suite never rewrites the other. Signing needs MSERIES_APT_KEY (an armored export of the
# signing subkey, mseries/release/KEY-RUNBOOK.md); without it this exits 1 and writes nothing.
# MSERIES_APT_KEY_PASSPHRASE is optional. KEEP bounds how many versions of each package the dev
# pool retains (stable keeps every release so a rollback can always fetch an old one).
set -euo pipefail

channel="" incoming="" tree=""
while (( $# > 0 )); do
  case $1 in
    --channel) channel=$2; shift 2 ;;
    --incoming) incoming=$2; shift 2 ;;
    --tree) tree=$2; shift 2 ;;
    *) echo "usage: $0 --channel dev|stable --incoming DIR --tree DIR" >&2; exit 2 ;;
  esac
done
case $channel in dev | stable) ;; *) echo "error: --channel must be dev or stable" >&2; exit 2 ;; esac
[[ -d $incoming ]] || { echo "error: --incoming '$incoming' is not a directory" >&2; exit 2; }
[[ -n $tree ]] || { echo "error: --tree is required" >&2; exit 2; }
KEEP=${KEEP:-8}

if [[ -z ${MSERIES_APT_KEY:-} ]]; then
  echo "MSERIES_APT_KEY is not set; refusing to publish an unsigned repo." >&2
  exit 1
fi
command -v apt-ftparchive >/dev/null || { echo "error: apt-ftparchive (apt-utils) is required" >&2; exit 1; }

shopt -s nullglob
debs=("$incoming"/*.deb)
(( ${#debs[@]} > 0 )) || { echo "error: no .deb files in $incoming" >&2; exit 1; }

# A throwaway keyring: the runner's own keyring is never touched.
GNUPGHOME=$(mktemp -d "${TMPDIR:-/tmp}/mseries-gnupg.XXXXXX")
export GNUPGHOME
chmod 0700 "$GNUPGHOME"
trap 'gpgconf --kill gpg-agent >/dev/null 2>&1 || true; rm -rf "$GNUPGHOME"' EXIT
gpg_opts=(--batch --yes --pinentry-mode loopback)
[[ -n ${MSERIES_APT_KEY_PASSPHRASE:-} ]] && gpg_opts+=(--passphrase-fd 3)
printf '%s' "$MSERIES_APT_KEY" | gpg --batch --import 2>/dev/null \
  || { echo "error: MSERIES_APT_KEY is not an importable PGP key" >&2; exit 1; }
fpr=$(gpg --batch --list-secret-keys --with-colons | awk -F: '$1 == "fpr" { print $10; exit }')
[[ -n $fpr ]] || { echo "error: MSERIES_APT_KEY holds no secret key" >&2; exit 1; }

sign() { # sign OUT IN GPG_MODE...
  local out=$1 in=$2
  shift 2
  if [[ -n ${MSERIES_APT_KEY_PASSPHRASE:-} ]]; then
    gpg "${gpg_opts[@]}" --local-user "$fpr" "$@" -o "$out" "$in" 3<<<"$MSERIES_APT_KEY_PASSPHRASE"
  else
    gpg "${gpg_opts[@]}" --local-user "$fpr" "$@" -o "$out" "$in"
  fi
}

pool=$tree/pool/$channel
dist=$tree/dists/$channel
mkdir -p "$pool"
cp -- "${debs[@]}" "$pool/"

# Retention, in dpkg's version order: newest KEEP per package. Stable is never pruned.
if [[ $channel == dev ]]; then
  python3 - "$pool" "$KEEP" <<'PY'
import functools, pathlib, subprocess, sys
pool, keep = pathlib.Path(sys.argv[1]), int(sys.argv[2])
def field(deb, name):
    return subprocess.check_output(["dpkg-deb", "-f", str(deb), name], text=True).strip()
def cmp(a, b):
    if subprocess.run(["dpkg", "--compare-versions", a[0], "lt", b[0]]).returncode == 0:
        return -1
    return 0 if a[0] == b[0] else 1
by_pkg = {}
for deb in pool.glob("*.deb"):
    by_pkg.setdefault(field(deb, "Package"), []).append((field(deb, "Version"), deb))
for pkg, items in by_pkg.items():
    items.sort(key=functools.cmp_to_key(cmp), reverse=True)
    for version, deb in items[keep:]:
        print(f"prune {pkg} {version}")
        deb.unlink()
PY
fi

# Fresh index every time, built from the pool, so a removed file leaves no stale entry.
bin=$dist/main/binary-arm64
rm -rf "$dist"
mkdir -p "$bin"
(cd "$tree" && apt-ftparchive packages "pool/$channel" > "dists/$channel/main/binary-arm64/Packages")
gzip -9nkf "$bin/Packages"
(cd "$dist" && apt-ftparchive \
  -o "APT::FTPArchive::Release::Origin=mseries" \
  -o "APT::FTPArchive::Release::Label=M-series elementary OS" \
  -o "APT::FTPArchive::Release::Suite=$channel" \
  -o "APT::FTPArchive::Release::Codename=$channel" \
  -o "APT::FTPArchive::Release::Architectures=arm64" \
  -o "APT::FTPArchive::Release::Components=main" \
  -o "APT::FTPArchive::Release::Description=M-series signed packages ($channel channel)" \
  release . > Release)
sign "$dist/InRelease" "$dist/Release" --clearsign
sign "$dist/Release.gpg" "$dist/Release" --armor --detach-sign

# Public half, for the keyring that mseries-update ships and for checking the fingerprint.
gpg --batch --export "$fpr" > "$tree/mseries-archive-keyring.gpg"
gpg --batch --armor --export "$fpr" > "$tree/mseries-archive-keyring.asc"

# Never leave a tree behind that the client side would reject: verify what was just written
# with the exported public key, the way apt will, and check every pool file against its index.
gpgv --keyring "$tree/mseries-archive-keyring.gpg" "$dist/InRelease" 2>/dev/null \
  || { echo "error: InRelease does not verify with the exported key" >&2; exit 1; }
gpgv --keyring "$tree/mseries-archive-keyring.gpg" "$dist/Release.gpg" "$dist/Release" 2>/dev/null \
  || { echo "error: Release.gpg does not verify with the exported key" >&2; exit 1; }
python3 - "$tree" "$channel" <<'PY'
import hashlib, pathlib, sys
tree, channel = pathlib.Path(sys.argv[1]), sys.argv[2]
index = (tree / "dists" / channel / "main/binary-arm64/Packages").read_text()
entries = [e for e in index.split("\n\n") if e.strip()]
on_disk = sorted(p.name for p in (tree / "pool" / channel).glob("*.deb"))
listed = []
for entry in entries:
    f = dict(l.split(": ", 1) for l in entry.splitlines() if ": " in l and not l.startswith(" "))
    deb = tree / f["Filename"]
    if hashlib.sha256(deb.read_bytes()).hexdigest() != f["SHA256"]:
        sys.exit(f"error: {f['Filename']} does not match its SHA256 in Packages")
    listed.append(deb.name)
if sorted(listed) != on_disk:
    sys.exit("error: pool and Packages disagree")
print(f"{channel}: {len(listed)} package files indexed, signed by the repository key")
PY
echo "key fingerprint: $fpr"
