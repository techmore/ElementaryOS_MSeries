#!/usr/bin/env bash
# EXPERIMENTAL: Omnissa's official x64 Horizon Client for Linux, run under FEX inside muvm (needs install-muvm.sh first).
# Omnissa ships no arm64 Linux build (only x64, and 32-bit armhf which Apple silicon cannot run). The proprietary
# tarball is downloaded from Omnissa at install time, checked against a pinned sha256, and never committed here.
#   install-horizon-client.sh             install under ~/.local/opt/omnissa-horizon
#   install-horizon-client.sh --uninstall remove it
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
command -v muvm >/dev/null || { echo 'Run mseries/install-muvm.sh first.' >&2; exit 1; }
ver=2606-8.19.0-32216036411
sha=e64a5900f7a26384776bc5912cb8d62e77565c686aae0eeb0b877a101a02d80a
url=https://download3.omnissa.com/software/CART27FQ2_LIN_2606_TARBALL/Omnissa-Horizon-Client-Linux-$ver.tar.gz
dest=$HOME/.local/opt/omnissa-horizon
bin=$HOME/.local/bin/horizon-client-x64
entry=$HOME/.local/share/applications/horizon-client-x64.desktop

if [[ ${1:-} == --uninstall ]]; then
  rm -rf "$dest" "$bin" "$entry"
  echo 'Removed.'
  exit 0
fi

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
curl -fL --silent --show-error "$url" -o "$tmp/h.tar.gz"
echo "$sha  $tmp/h.tar.gz" | sha256sum -c -
tar xzf "$tmp/h.tar.gz" -C "$tmp"
rm -rf "$dest"; mkdir -p "$dest"
for part in Client PCoIP; do
  tar xzf "$tmp"/*/x64/Omnissa-Horizon-$part-"$ver".x64.tar.gz -C "$dest" --strip-components=1
done

# Ubuntu 24.04 x64 libraries the FEX rootfs lacks (pinned path + sha256 from the noble archive index).
while read -r file digest; do
  curl -fsS "https://archive.ubuntu.com/ubuntu/$file" -o "$tmp/lib.deb"
  echo "$digest  $tmp/lib.deb" | sha256sum -c - >/dev/null
  dpkg-deb -x "$tmp/lib.deb" "$dest/extra"
done <<LIBS
  pool/main/libx/libxkbfile/libxkbfile1_1.1.0-1build4_amd64.deb 22ac5b7dca740e606261cebdfaf1a07738e92ad3d123570694374ddb4d5afea2
  pool/main/p/pcsc-lite/libpcsclite1_2.0.3-1build1_amd64.deb 703bacc9204a7ecc24486ac8c96d15d0b9e2c91c385388e132ad4fd8f56f035a
  pool/main/v/v4l-utils/libv4l-0t64_1.26.1-4build3_amd64.deb 0cafac8bb1fca1ae042cd11d40e06412a8958e1a6faf268df421f4762989a6d9
  pool/main/u/ust/liblttng-ust1t64_2.13.7-1.1ubuntu2_amd64.deb 020744e76395d7a5e7134a0a9f5a7fc7bdee4d1b769db9dd1be068f96c778d85
  pool/main/u/ust/liblttng-ust-common1t64_2.13.7-1.1ubuntu2_amd64.deb 0e25a34ca6887fbbcef70c49d19aae6df448b3f1f469e118973e9fe39d75d463
  pool/main/u/ust/liblttng-ust-ctl5t64_2.13.7-1.1ubuntu2_amd64.deb c01835be62638243b60e03768620c2f2057979f68f8e46d35c15a9cbb35aa213
  pool/main/v/v4l-utils/libv4lconvert0t64_1.26.1-4build3_amd64.deb 67811cffddbf1e601f5630d733455a26c1cadb6bc28795e5b673be82b55113b4
  pool/main/libu/liburcu/liburcu8t64_0.14.0-3.1build1_amd64.deb 1e0545f27be0dd31bf017f277b13cac9a7857efef7324ca83527e3213e717181
  pool/main/n/numactl/libnuma1_2.0.18-1ubuntu0.24.04.1_amd64.deb f333b8edf6f0b705c19f2a67008194df66f7aab0fa2350dc98510569a033ff29
LIBS

mkdir -p "$(dirname "$bin")" "$(dirname "$entry")"
cat >"$dest/run.sh" <<RUN
#!/bin/bash
# Runs inside the FEX x64 rootfs.
export LD_LIBRARY_PATH=$dest/usr/lib:$dest/usr/lib/omnissa:$dest/extra/usr/lib/x86_64-linux-gnu
shift  # drop the -- that keeps FEXBash from reading client flags such as --help
exec $dest/usr/lib/omnissa/horizon/bin/horizon-client "\$@"
RUN
chmod +x "$dest/run.sh"
cat >"$bin" <<WRAP
#!/usr/bin/env bash
# x64 Horizon Client under FEX in a 4 KB-page microVM (see mseries/HORIZON-CLIENT.md).
exec muvm -- FEXBash $dest/run.sh -- "\$@"
WRAP
chmod +x "$bin"
cat >"$entry" <<DESK
[Desktop Entry]
Type=Application
Name=Omnissa Horizon Client (x64, emulated)
Exec=$bin
Icon=preferences-desktop-remote-desktop
Terminal=false
Categories=Network;RemoteAccess;
DESK
echo "Installed to $dest. Launch with horizon-client-x64. Verified: --help runs under FEX/muvm; broker login and Blast sessions are untested."
