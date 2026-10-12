#!/bin/bash
# fairydust-build.sh — build + install the fairydust USB-C DP-Alt-Mode kernel
# on this machine, from the elementary side, by chrooting into the Arch (@)
# root. Survives reboots. Run:
#
#     sudo /home/admin/fairydust-build.sh
#
# NOTES / WHY THIS IS A SCRIPT
#   * The first attempt bind-mounted the HOST /run into the chroot; something
#     in the Arch build wiped /run/user/1000 and killed the live session bus +
#     Wayland socket (top bar gone). This version mounts a PRIVATE tmpfs /run,
#     so the host session is never touched.
#   * pacman's disk-space check misfires in a chroot (btrfs) -> CheckSpace off.
#   * The Arch /home subvolume (@home) must be mounted or rustup can't write.
#   * The private /run also hides systemd-resolved's stub resolver, so the
#     chroot's (symlinked) /etc/resolv.conf is populated from the host's real
#     upstream servers — otherwise pacman/makepkg can't resolve any mirror.
set -euo pipefail

REPO=${REPO:-/home/admin/ElementaryOS_MSeries}
KIT="$REPO/mseries/fairydust"
TOROOT=/mnt/fdbuild/top
R=/mnt/fdbuild/root
DRIVER=/home/admin/fairydust-driver.sh

[[ $EUID -eq 0 ]] || { echo "run me as root (sudo)." >&2; exit 1; }
[[ -f $DRIVER ]] || { echo "missing $DRIVER" >&2; exit 1; }
[[ -f $KIT/PKGBUILD ]] || { echo "missing $KIT/PKGBUILD (clone the repo?)" >&2; exit 1; }

cleanup() {
  for m in "$R/etc/hosts" "$R/boot" "$R/home" "$R/run" "$R/sys" "$R/proc" "$R/dev"; do
    umount -R "$m" 2>/dev/null || true
  done
  umount "$R" 2>/dev/null || true
  umount "$TOROOT" 2>/dev/null || true
}
trap cleanup EXIT

mkdir -p "$TOROOT" "$R"
mount -o subvolid=5 /dev/mapper/root "$TOROOT"
mount -o subvol=@ /dev/mapper/root "$R"

mkdir -p "$R/dev" "$R/proc" "$R/sys" "$R/run" "$R/home" "$R/boot"
mount --bind /dev  "$R/dev"
mount --bind /proc "$R/proc"
mount --bind /sys  "$R/sys"
mount -t tmpfs -o mode=755 tmpfs "$R/run"        # PRIVATE — do not touch host /run
mount --bind /boot "$R/boot"
mount -o subvol=@home /dev/mapper/root "$R/home"

# DNS for the chroot. /etc/resolv.conf is a symlink to
# /run/systemd/resolve/stub-resolv.conf, and the private /run above means that
# target no longer exists. Recreate it on the tmpfs (ephemeral — the Arch
# subvolume is untouched). Public resolvers are used first: the host's
# upstream resolver rate-limits pacman's concurrent libcurl lookups ("Could
# not resolve host") even though glibc/getent succeeds, so it goes last as a
# fallback only.
tmp_resolv=$(mktemp)
{
  printf 'nameserver 1.1.1.1\nnameserver 8.8.8.8\nnameserver 9.9.9.9\n'
  host_resolv=/run/systemd/resolve/resolv.conf
  [[ -s $host_resolv ]] || host_resolv=/etc/resolv.conf
  grep '^nameserver' "$host_resolv" 2>/dev/null | grep -v '127\.0\.0\.53' || true
} > "$tmp_resolv"

# Write the real file rather than through the (possibly dangling) symlink:
# resolve $R/etc/resolv.conf's symlink target and create that, so the target
# stays on the private tmpfs.
resolv=$R/etc/resolv.conf
if [[ -L $resolv ]]; then
  link=$(readlink -- "$resolv")
  case $link in
    /*) resolv="$R$link" ;;
    *)  resolv="$(dirname -- "$resolv")/$link" ;;
  esac
fi
resolv=$(realpath -m -- "$resolv")
install -d "$(dirname -- "$resolv")"
cp -f "$tmp_resolv" "$resolv"
rm -f "$tmp_resolv"
echo ">>> chroot DNS: $(grep -h '^nameserver' "$R/etc/resolv.conf" 2>/dev/null | tr '\n' ' ')"

# Belt-and-suspenders for the flaky resolver: pin every host we know the build
# needs in the chroot's /etc/hosts. glibc and libcurl consult "files" before
# "dns" (nsswitch), so pacman/makepkg then don't depend on the resolver at all.
# Generated on the private tmpfs and bind-mounted, so the Arch subvolume's
# /etc/hosts is left untouched.
hosts_src=$R/run/fairydust-hosts
{
  cat "$R/etc/hosts" 2>/dev/null || true
  {
    # Every pacman repo host, including mirrorlist includes.
    grep -rhoE 'https?://[^/$ ]+' "$R/etc/pacman.conf" "$R/etc/pacman.d/" 2>/dev/null \
      | sed -E 's#https?://##'
    # Hosts makepkg/rustup reach that aren't in pacman's config.
    printf '%s\n' \
      codeload.github.com objects.githubusercontent.com \
      release-assets.githubusercontent.com raw.githubusercontent.com \
      static.rust-lang.org sh.rustup.rs rustup.rs forge.rust-lang.org \
      distribution.rust-lang.org
  } | sort -u | while read -r h; do
      [[ -n $h ]] || continue
      # getent returns non-zero for hosts that don't resolve; don't let that
      # (with set -e + pipefail) kill the build.
      ip=$(getent ahostsv4 "$h" 2>/dev/null | awk 'NR==1{print $1}') || ip=
      if [[ -n $ip ]]; then printf '%s %s\n' "$ip" "$h"; fi
    done
} > "$hosts_src" || true
if mount --bind "$hosts_src" "$R/etc/hosts"; then
  echo ">>> chroot /etc/hosts pins: $(grep -cvE '^#|^$' "$hosts_src") entries"
else
  echo ">>> WARNING: could not bind /etc/hosts pins; using DNS only" >&2
fi

sed -i 's/^CheckSpace/#CheckSpace/' "$R/etc/pacman.conf"

install -d "$R/root/fairydust-kit"
cp -a "$KIT"/. "$R/root/fairydust-kit/"
cp "$DRIVER" "$R/root/fairydust-driver.sh"
chmod +x "$R/root/fairydust-driver.sh"

echo ">>> entering chroot build (1-3 hours). Log: /tmp/opencode/fairydust-build.log"
chroot "$R" /bin/bash /root/fairydust-driver.sh
