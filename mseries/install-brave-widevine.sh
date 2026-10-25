#!/usr/bin/env bash
# Widevine DRM for Brave on Apple Silicon (arm64 Linux), so rented/purchased YouTube movies and other DRM video play.
#   bash mseries/install-brave-widevine.sh              # install; quit Brave first
#   bash mseries/install-brave-widevine.sh --uninstall  # remove the component and the opt-in
# Uses Google's own Linux arm64 Widevine component (the one Brave documents for arm64), pinned by size and SHA-512 from
# Mozilla bug 1612995 comment 17. Nothing is patched. Playback is software-level (L3): services cap it at SD/720p.
# See mseries/BRAVE-WIDEVINE.md.
set -euo pipefail
version=4.10.3057.0
url=https://dl.google.com/release2/chrome_component/bar3g6bc54wcbgowdtlox2l3sa_${version}/oimompecagnajdejgnnjijobebaeigek_${version}_linux_arm64_h5xzghmkhfkkto65d2lfjxatgm.crx3
size=19826058
sha512=2a5ad41d5037a1e9cbfe30a94653f49247c628278f922d5aab20566fac874685ef8312f482e5bd23bdd88ecce98dc0c468c979637ebdb1174cc2801f8ffde8c6
profile=${BRAVE_PROFILE_DIR:-${XDG_CONFIG_HOME:-$HOME/.config}/BraveSoftware/Brave-Browser}
cdm=$profile/WidevineCdm

[[ $(uname -m) == aarch64 ]] || { echo 'This is for arm64 Linux only.' >&2; exit 1; }
if [[ -n ${BRAVE_PROFILE_DIR:-} ]]; then running() { pgrep -u "$USER" -f -- "--user-data-dir=$profile( |$)" >/dev/null; }  # a separate profile, e.g. brave-youtube
else running() { pgrep -u "$USER" -x brave >/dev/null; }; fi
if running; then echo 'Quit Brave completely first (it rewrites its preferences on exit).' >&2; exit 1; fi
[[ -f $profile/Local\ State ]] || { echo "No Brave profile at $profile. Start Brave once, quit it, and re-run." >&2; exit 1; }

set_optin() {  # $1 = true|false
  python3 -I - "$profile/Local State" "$1" <<'PY'
import json, shutil, sys
path, value = sys.argv[1], sys.argv[2] == 'true'
shutil.copy2(path, path + '.before-widevine')
with open(path) as f:
    state = json.load(f)
state.setdefault('brave', {})['widevine_opted_in'] = value
with open(path, 'w') as f:
    json.dump(state, f, separators=(',', ':'))
PY
}

if [[ ${1:-} == --uninstall ]]; then
  rm -rf "$cdm"
  set_optin false
  echo 'Removed. Restart Brave.'
  exit 0
fi

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -fsS --connect-timeout 15 --max-time 120 --max-redirs 0 -o "$tmp/wv.crx3" "$url"
[[ $(stat -c %s "$tmp/wv.crx3") == "$size" ]] || { echo 'Download size mismatch.' >&2; exit 1; }
[[ $(sha512sum "$tmp/wv.crx3" | cut -d' ' -f1) == "$sha512" ]] || { echo 'Download SHA-512 mismatch.' >&2; exit 1; }

# A .crx3 is a zip with a header; unzip warns about the header and extracts anyway.
unzip -q "$tmp/wv.crx3" -d "$tmp/x" 2>/dev/null || [[ -f $tmp/x/manifest.json ]]
lib=$tmp/x/_platform_specific/linux_arm64/libwidevinecdm.so
[[ -f $lib ]] || { echo 'Archive has no linux_arm64 library.' >&2; exit 1; }
python3 -I -c 'import ctypes,sys; ctypes.CDLL(sys.argv[1])' "$lib" || { echo 'Library does not load on this system.' >&2; exit 1; }

dest=$cdm/$version
rm -rf "$dest"; install -d -m 0755 "$dest"
cp -r "$tmp/x/." "$dest/"
chmod -R u+rwX,go+rX "$dest"
printf '{"Path":"%s"}\n' "$dest" > "$cdm/latest-component-updated-widevine-cdm"
set_optin true
echo "Widevine $version installed for Brave. Start Brave; check brave://components."
