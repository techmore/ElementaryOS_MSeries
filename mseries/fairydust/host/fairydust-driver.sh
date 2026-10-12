#!/bin/bash
# fairydust-driver.sh — runs INSIDE the Arch (@) chroot as root.
# Builds linux-asahi-fairydust via the kit's PKGBUILD, installs it beside
# stock linux-asahi, rebuilds initramfs, refreshes m1n1 DTBs + GRUB.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C

log() { echo "[fairydust] $*"; }

# The mirror/DNS path on this network is intermittently flaky (pacman's
# libcurl bursts queries and occasionally gets "Could not resolve host" even
# though getent succeeds). Retry every network step.
retry() {
  local desc=$1; shift
  local n
  for n in 1 2 3 4 5 6; do
    if "$@"; then return 0; fi
    log "$desc failed (attempt $n/6); retrying in 5s..."
    sleep 5
  done
  log "$desc failed after 6 attempts"
  return 1
}

KIT=/root/fairydust-kit
BUILDDIR=/home/techmore/fairydust

log "syncing pacman DB + installing build deps"
retry "pacman sync+deps" pacman -Sy --needed --noconfirm --disable-download-timeout \
  base-devel bc dtc kmod libelf pahole cpio perl rustup rust-bindgen \
  tar xz xmlto python git

log "staging kit in $BUILDDIR"
install -d -o techmore -g techmore "$BUILDDIR"
cp -a "$KIT"/. "$BUILDDIR"/
zcat /proc/config.gz > "$BUILDDIR/config"
chown -R techmore:techmore "$BUILDDIR"

log "installing Rust toolchain (stable, for the Asahi kernel tree)"
retry "rustup toolchain install" \
  runuser -l techmore -c 'rustup toolchain install stable --profile minimal --component rust-src' \
  || retry "rustup default stable" runuser -l techmore -c 'rustup default stable'

log "building (1-3 hours) — makepkg as techmore"
# makepkg's only network step is the source tarball fetch, which happens
# before the long compile, so a retry is cheap in the common failure case.
retry "makepkg" \
  runuser -l techmore -c "cd '$BUILDDIR' && makepkg --cleanbuild --force --noconfirm"

pkg=$(ls "$BUILDDIR"/linux-asahi-fairydust-*.pkg.tar.* | head -n1)
log "installing $pkg"
pacman -U --noconfirm "$pkg"

kver=$(ls /usr/lib/modules | grep fairydust | head -n1)
[[ -n $kver ]] || { echo "no fairydust modules installed" >&2; exit 1; }
log "fairydust kernel release: $kver"

install -Dm644 "/usr/lib/modules/$kver/vmlinuz" /boot/vmlinuz-linux-asahi-fairydust

cat > /etc/mkinitcpio.d/linux-asahi-fairydust.preset <<EOF
ALL_config="/etc/mkinitcpio.conf"
ALL_kver="/boot/vmlinuz-linux-asahi-fairydust"
PRESETS=('default')
default_image="/boot/initramfs-linux-asahi-fairydust.img"
EOF
log "building initramfs (mirrors stock linux-asahi hooks)"
mkinitcpio -P

log "refreshing m1n1 stage-2 with fairydust DTBs"
DTBS="/usr/lib/modules/$kver/dtbs/*.dtb" update-m1n1

log "regenerating GRUB menu"
grub-mkconfig -o /boot/grub/grub.cfg

log "DONE. fairydust=$kver"
ls -la /boot/ | grep -i fairydust
