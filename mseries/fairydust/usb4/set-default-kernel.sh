#!/usr/bin/env bash
# Select the installed Fairydust USB4 entry persistently; retain stock recovery.
# Preview: bash mseries/fairydust/usb4/set-default-kernel.sh
# Apply: sudo bash mseries/fairydust/usb4/set-default-kernel.sh --apply
set -euo pipefail
apply=0
case ${1:-} in
  '') ;;
  --apply) apply=1 ;;
  *) echo "Usage: $0 [--apply]" >&2; exit 2 ;;
esac
cfg=/boot/grub/custom.cfg
for path in /boot/vmlinuz-linux-asahi-fairydust-usb4 /boot/initramfs-linux-asahi-fairydust-usb4.img /boot/vmlinuz-linux-asahi /boot/initramfs-linux-asahi.img; do
  [[ -s $path ]] || { echo "Missing boot file: $path" >&2; exit 1; }
done
grep -q -- '--id elementary-usb4-test' "$cfg"
grep -q -- '--id elementary-mseries' /boot/grub/grub.cfg
grep -q 'source .*custom.cfg' /boot/grub/grub.cfg
[[ -d /usr/lib/modules/7.1.13-elementary-fairydust-usb4 ]] || {
  echo 'Matching Fairydust modules are missing; refusing to change the default.' >&2
  exit 1
}
echo 'Default: elementary-usb4-test (Fairydust USB4)'
echo 'Recovery: elementary-mseries (stock kernel); boot menu visible for 5 seconds'
(( apply )) || { echo 'Preview only. Use --apply with sudo to save.'; exit 0; }
(( EUID == 0 )) || { echo 'Apply requires sudo.' >&2; exit 1; }
cp -a "$cfg" "$cfg.before-fairydust-default-$(date +%Y%m%d-%H%M%S)"
python3 - "$cfg" <<'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
start = '# BEGIN elementary Fairydust default'
end = '# END elementary Fairydust default'
text = path.read_text()
if start in text:
    before, rest = text.split(start, 1)
    _, after = rest.split(end, 1)
    text = before + after
block = '''# BEGIN elementary Fairydust default
# Preserve one-time selections made by grub-reboot.
if [ "${boot_once}" != "true" ]; then
    set default="elementary-usb4-test"
fi
set fallback="elementary-mseries"
set timeout_style=menu
set timeout=5
# END elementary Fairydust default
'''
path.write_text(text.rstrip() + '\n\n' + block)
PY
echo 'Saved. Reboot when ready; stock recovery remains selectable in GRUB.'
