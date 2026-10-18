#!/bin/bash
# x86-64 emulation on this 16 KB-page kernel: FEX (from its PPA) runs inside a 4 KB-page microVM (muvm + libkrun
# + libkrunfw, built from source at pinned tags). FEX alone aborts here ("<jemalloc>: Unsupported system page
# size"). Verified 2026-10-18: `muvm -- FEXBash -c 'uname -m; getconf PAGESIZE'` prints x86_64 and 4096.
# Installs under /usr/local and /etc (apt source, ld.so.conf); nothing is registered with binfmt on the host.
#   install-muvm.sh             install
#   install-muvm.sh --uninstall remove binaries, libs and the FEX apt source (keeps the rootfs in ~/.local/share/fex-emu)
set -euo pipefail
[[ $(uname -m) == aarch64 ]] || { echo 'This installer requires ARM64' >&2; exit 1; }
repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
source "$repo/mseries/lib-apt.sh"
if [[ ${1:-} == --uninstall ]]; then
  sudo rm -f /usr/local/bin/muvm /usr/local/bin/muvm-guest /etc/ld.so.conf.d/mseries-libkrun.conf \
    /usr/local/lib64/libkrun.so* /usr/local/lib/aarch64-linux-gnu/libkrunfw.so* \
    /etc/apt/sources.list.d/fex-emu.list /usr/share/keyrings/fex-emu-ppa.gpg
  sudo ldconfig
  echo 'Removed muvm, libkrun, libkrunfw and the FEX apt source. fex-emu-armv8.4 stays; remove with apt if wanted.'
  exit 0
fi
[[ -r /dev/kvm && -w /dev/kvm ]] || { echo '/dev/kvm is not accessible to this user' >&2; exit 1; }
# FEX PPA key: the signer of the resolute InRelease; the fingerprint is pinned and checked after download.
fex_fpr=EDB98BFE8A2310DC9C4A376E76DBFEBEA206F5AC
muvm_tag=muvm-0.7.0 krun_tag=v1.19.6 krunfw_tag=v5.6.2
build=${MSERIES_BUILD_DIR:-$HOME/.cache/mseries-build/muvm}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
curl -fsS "https://keyserver.ubuntu.com/pks/lookup?op=get&search=0x$fex_fpr" -o "$work/key.asc"
gpg --show-keys --with-colons "$work/key.asc" | grep -q "^fpr:::::::::$fex_fpr:" \
  || { echo 'FEX PPA key fingerprint mismatch' >&2; exit 1; }
gpg --dearmor <"$work/key.asc" >"$work/fex.gpg"
sudo install -Dm644 "$work/fex.gpg" /usr/share/keyrings/fex-emu-ppa.gpg
echo 'deb [arch=arm64 signed-by=/usr/share/keyrings/fex-emu-ppa.gpg] https://ppa.launchpadcontent.net/fex-emu/fex/ubuntu resolute main' \
  | sudo tee /etc/apt/sources.list.d/fex-emu.list >/dev/null
mseries_apt_refresh
sudo apt-get install -y --no-install-recommends fex-emu-armv8.4 passt \
  clang libclang-dev flex bison bc libelf-dev python3-pyelftools libvirglrenderer-dev libepoxy-dev \
  libdrm-dev libpipewire-0.3-dev libcap-ng-dev libssl-dev libudev-dev libgbm-dev pkg-config patch xz-utils
mkdir -p "$build"
cd "$build"
clone() { [[ -d $2 ]] || git clone -q --depth 1 --branch "$3" "https://github.com/$1.git" "$2"; }
clone containers/libkrunfw libkrunfw "$krunfw_tag"
clone containers/libkrun libkrun "$krun_tag"
clone AsahiLinux/muvm muvm "$muvm_tag"
# libkrunfw's default aarch64 guest config is CONFIG_ARM64_4K_PAGES=y, which is the point of the VM.
grep -q '^CONFIG_ARM64_4K_PAGES=y' libkrunfw/config-libkrunfw_aarch64
make -C libkrunfw -j"$(nproc)"
make -C libkrun BLK=1 NET=1 GPU=1 SND=1
sudo make -C libkrunfw install PREFIX=/usr/local
sudo make -C libkrun install PREFIX=/usr/local BLK=1 NET=1 GPU=1 SND=1
printf '/usr/local/lib64\n' | sudo tee /etc/ld.so.conf.d/mseries-libkrun.conf >/dev/null
sudo ldconfig
(cd muvm && PKG_CONFIG_PATH=/usr/local/lib64/pkgconfig cargo build --release --locked)
sudo install -m755 muvm/target/release/muvm muvm/target/release/muvm-guest /usr/local/bin/
# x86-64 Ubuntu rootfs for FEX, plus the config the fetcher fails to write.
FEXRootFSFetcher -y -x --distro-name=ubuntu --distro-version=24.04 --force-ui=tty
mkdir -p "$HOME/.config/fex-emu"
[[ -f $HOME/.config/fex-emu/Config.json ]] \
  || printf '{"Config":{"RootFS":"Ubuntu_24_04"}}\n' >"$HOME/.config/fex-emu/Config.json"
out=$(muvm -- FEXBash -c 'uname -m; getconf PAGESIZE' 2>&1 | tr '\n' ' ')
[[ $out == *x86_64*4096* ]] || { echo "muvm/FEX self-test failed: $out" >&2; exit 1; }
echo 'muvm + FEX OK: x86_64 with 4096-byte pages inside the microVM.'
