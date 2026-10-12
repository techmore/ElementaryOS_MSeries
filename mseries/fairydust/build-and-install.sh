#!/usr/bin/env bash
# build-and-install.sh — build & install the Fairydust DP-Alt-Mode kernel on
# Asahi Arch / omarchy-mac. Adapted from Grzegorz Smajdor's kit (GPL-2.0),
# retargeted to apple,j314s (M1 Pro 14") / Asahi 7.1.13-3.
#
# Run on the ARCH side (Omarchy), as your normal user (uses sudo internally).
# See README.md — produce `config` and `fairydust.patch` first.
set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$script_dir"

# --- preflight -------------------------------------------------------------
[[ $(uname -m) == aarch64 ]] \
  || { echo "This kernel must be built natively on aarch64." >&2; exit 1; }

# Models the fairydust DT patches bless a port on (t8103 / t60xx / t8112).
compat=$(tr '\0' '\n' </proc/device-tree/compatible 2>/dev/null || true)
if ! grep -Eq '^apple,(j314s?|j316s?|j414s?|j416s?|j274|j293|j313|j4125|j185|j493|j473|j474|j475|j485|j487)$' <<<"$compat"; then
  echo "WARNING: $(grep -m1 '^apple,' <<<"$compat" || echo unknown) is not in the" >&2
  echo "         known fairydust dp-altmode model list." >&2
  echo "         Confirm the branch has a dp-altmode DT patch for it." >&2
  read -rp "Continue anyway? [y/N] " a; [[ $a == [yY] ]] || exit 1
fi

[[ -e /etc/pacman.conf ]] \
  || { echo "Arch/ALARM required (no /etc/pacman.conf). Run this on Omarchy." >&2; exit 1; }

available_kib=$(df --output=avail -k "$script_dir" | tail -n 1 | tr -d ' ')
required_kib=$((35 * 1024 * 1024))
(( available_kib >= required_kib )) \
  || { echo "Need >= 35 GiB free for the kernel build." >&2; exit 1; }

for f in config fairydust.patch; do
  [[ -f $f ]] || { echo "Missing ./$f — see README.md ('Two files you must generate')." >&2; exit 1; }
done

# --- dependencies ----------------------------------------------------------
echo "Installing kernel build dependencies..."
sudo pacman -S --needed --noconfirm \
  base-devel bc dtc kmod libelf pahole cpio perl rustup rust-bindgen \
  tar xz xmlto python pacman-contrib

# Rust version the kernel expects. Override with RUST_TOOLCHAIN=... if a
# newer fairydust base needs a newer compiler.
RUST_TOOLCHAIN="${RUST_TOOLCHAIN:-1.93.1}"
echo "Installing Rust $RUST_TOOLCHAIN (required by the Asahi tree)..."
rustup toolchain install "$RUST_TOOLCHAIN" --profile minimal --component rust-src
export RUSTUP_TOOLCHAIN="$RUST_TOOLCHAIN"

# --- build -----------------------------------------------------------------
echo "Building with makepkg (1-3 hours)..."
makepkg --cleanbuild --force

mapfile -t packages < <(
  find "$script_dir" -maxdepth 1 -type f \
    -name 'linux-asahi-fairydust-[0-9]*-aarch64.pkg.tar.*' -print | sort
)
(( ${#packages[@]} == 1 )) \
  || { echo "Expected exactly one Fairydust package; found ${#packages[@]}." >&2; exit 1; }

sudo pacman -U --needed "${packages[0]}"
sudo mkinitcpio -P

# --- m1n1 device tree + GRUB ----------------------------------------------
fairydust_modules=$(find /usr/lib/modules -mindepth 1 -maxdepth 1 -type d \
  -name '*fairydust*' -print | sort -V | tail -n 1)
[[ -n $fairydust_modules && -d $fairydust_modules/dtbs ]] \
  || { echo "Fairydust modules/DTB dir not found." >&2; exit 1; }

# m1n1 stage 2 must carry the DTBs with the Alt Mode nodes. Asahi ALARM
# ships the DTBs flat in dtbs/ (not dtbs/apple/).
sudo env DTBS="$fairydust_modules/dtbs/*.dtb" update-m1n1
sudo grub-mkconfig -o /boot/grub/grub.cfg

echo
echo "Fairydust installed alongside stock linux-asahi."
echo "Reboot, pick the fairydust entry in GRUB (put the dock on the FRONT-LEFT"
echo "USB-C port), then run ./verify.sh."
