#!/bin/bash
# Put the elementary OS Plymouth theme on the disk-encryption passphrase screen.
#
# The Asahi Alarm (Arch) side owns the initramfs for both systems, so this runs
# there as root. It is what bin/elementary-mac-setup uses for the "unlock
# screen" and replaces the Omarchy lock/entry splash with elementary's own
# (logo, passphrase entry, keyboard-layout and caps-lock badges).
#
#   sudo mseries/install-unlock-screen.sh --theme-from DIR   install + rebuild
#   sudo mseries/install-unlock-screen.sh --uninstall        undo
#
# DIR is a plymouth-theme-elementary tree (usr/share/plymouth/themes/elementary),
# normally taken from the freshly built @elementary subvolume.
#
# Safety: backs up /etc/mkinitcpio.conf and every initramfs on the ESP, rebuilds,
# checks that the new images still carry btrfs + dm-crypt + the theme, and puts
# the backups back if they do not.
set -euo pipefail

THEME=elementary
THEME_DST=/usr/share/plymouth/themes/$THEME
PLYMOUTHD=/etc/plymouth/plymouthd.conf
MKCONF=/etc/mkinitcpio.conf
DROPIN=/etc/mkinitcpio.conf.d/zz_elementary_unlock.conf
STAMP=pre-elementary-unlock

log()  { printf '\033[32m==>\033[0m %s\n' "$*"; }
fail() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

[[ $EUID -eq 0 ]] || fail "run as root"

images() { compgen -G '/boot/initramfs-*.img' || true; }

restore() {
  local img
  [[ -f $MKCONF.$STAMP ]] && cp -a "$MKCONF.$STAMP" "$MKCONF"
  for img in /boot/initramfs-*.img."$STAMP"; do
    [[ -f $img ]] && cp -a "$img" "${img%."$STAMP"}"
  done
  unlink "$DROPIN" 2>/dev/null || true
  return 0
}

if [[ ${1:-} == --uninstall ]]; then
  bash "$(dirname "$0")/boot/mkinitcpio-snippet" remove initramfs-splash
  unlink "$DROPIN" 2>/dev/null || true
  [[ -f $PLYMOUTHD ]] && sed -i 's/^Theme=elementary/Theme=omarchy/' "$PLYMOUTHD"
  mkinitcpio -P
  echo "Removed the elementary unlock screen hooks and rebuilt the initramfs."
  exit 0
fi

[[ ${1:-} == --theme-from && -n ${2:-} ]] || fail "usage: $0 --theme-from DIR | --uninstall"
SRC=$2
[[ -f $SRC/$THEME.plymouth ]] || fail "$SRC is not an elementary plymouth theme"

# One backup of every image plus room to rebuild them (the ESP is small FAT).
used_mb=0
for img in $(images); do used_mb=$(( used_mb + $(stat -c %s "$img") / 1048576 + 1 )); done
need_mb=$(( used_mb * 2 + 10 ))
avail_mb=$(df -m --output=avail /boot | tail -1)
(( avail_mb > need_mb )) || fail "only ${avail_mb}MB free on /boot; need about ${need_mb}MB for backups and the rebuild"

command -v plymouth >/dev/null || pacman -S --noconfirm --needed plymouth ||
  fail "could not install plymouth"
# Inter is elementary's UI font; Noto is the fallback if it is not packaged.
pacman -S --noconfirm --needed inter-font >/dev/null 2>&1 ||
  pacman -S --noconfirm --needed noto-fonts >/dev/null 2>&1 || true

font=Inter
fc-list : family 2>/dev/null | grep -qiE '^Inter(,|$)' || font='Noto Sans'

# Back up first, once.
cp -a "$MKCONF" "$MKCONF.$STAMP"
for img in $(images); do
  [[ -f $img.$STAMP ]] || cp -a "$img" "$img.$STAMP"
done

# Replace any earlier copy of the theme (a re-run, or an older version).
[[ $THEME_DST == /usr/share/plymouth/themes/elementary ]] && [[ -d $THEME_DST ]] && rm -r "$THEME_DST"
mkdir -p "$(dirname "$THEME_DST")"
cp -a "$SRC" "$THEME_DST"
sed -i "s|^Font=.*|Font=$font 12|; s|^TitleFont=.*|TitleFont=$font Bold 32|; s|^ImageDir=.*|ImageDir=$THEME_DST|" \
  "$THEME_DST/$THEME.plymouth"

mkdir -p "$(dirname "$PLYMOUTHD")"
if grep -q '^Theme=' "$PLYMOUTHD" 2>/dev/null; then
  sed -i 's/^Theme=.*/Theme=elementary/' "$PLYMOUTHD"
else
  printf '[Daemon]\nTheme=elementary\nShowDelay=0\n' >"$PLYMOUTHD"
fi

# HOOKS: plymouth before encrypt so the passphrase is asked on the splash,
# keyboard to type it, kms so the display is up for it, keymap/consolefont so it
# is typed under the right layout. The block goes into mkinitcpio.conf itself
# (see mkinitcpio-snippet for why drop-ins are not enough).
unlink "$DROPIN" 2>/dev/null || true   # older versions of this script used a drop-in
bash "$(dirname "$0")/boot/mkinitcpio-snippet" add initramfs-splash

log "Rebuilding the initramfs"
if ! mkinitcpio -P; then
  restore
  fail "mkinitcpio failed; backups restored"
fi

for img in $(images); do
  listing=$(lsinitcpio "$img" 2>/dev/null) || { restore; fail "cannot read $img; backups restored"; }
  for need in btrfs dm-crypt "themes/$THEME"; do
    grep -q "$need" <<<"$listing" || { restore; fail "$img is missing $need; backups restored"; }
  done
done

log "elementary unlock screen installed. Backups: $MKCONF.$STAMP and /boot/*.$STAMP"
log "Undo with: $0 --uninstall"
