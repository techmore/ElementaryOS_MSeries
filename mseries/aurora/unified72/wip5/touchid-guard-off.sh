#!/usr/bin/env bash
# 1) Byte-exact, read-only backup of the Apple boot container (xART lives there) and the two small
#    Apple NVMe namespaces. 2) Add a separate wip5 boot entry with apple_sep.xart_guard=0.
#    The normal wip5 entry keeps the guard on; wip4 stays the default. Nothing is armed.
# Run: sudo bash ~/.cache/mseries-kernel/wip5/touchid-guard-off.sh
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'run with sudo' >&2; exit 1; }
cfg=/boot/grub/custom.cfg
ts=$(date -u +%Y%m%dT%H%M%SZ)
dir=/var/lib/mseries-kernel-tests/xart-backup-$ts
mkdir -p "$dir"; chmod 700 "$dir"

# Step 1: backup. Read-only dd; abort before touching anything if any copy fails to verify.
for dev in nvme0n1p1 nvme0n2 nvme0n3; do
  [[ -b /dev/$dev ]] || { echo "missing /dev/$dev" >&2; exit 1; }
  dd if=/dev/$dev of="$dir/$dev.img" bs=4M iflag=direct status=none
  a=$(sha256sum < "$dir/$dev.img" | cut -c1-64); b=$(sha256sum < /dev/$dev | cut -c1-64)
  [[ $a == "$b" ]] || { echo "backup of $dev does not match the device" >&2; exit 1; }
  echo "$a  $dev.img" >> "$dir/SHA256SUMS"
done
lsblk -o NAME,SIZE,PARTLABEL,PARTUUID /dev/nvme0n1 /dev/nvme0n2 /dev/nvme0n3 > "$dir/layout.txt"
chmod 600 "$dir"/*
echo "backup verified: $dir"; cat "$dir/SHA256SUMS"

# Step 2: guard-off boot entry, copied from the wip5 trial entry.
cp -a "$cfg" "$dir/custom.cfg.before"
if ! grep -q 'elementary-aurora72-wip5-xartguard-off-trial' "$cfg"; then
  python3 - "$cfg" <<'PY'
import re, sys
p = sys.argv[1]; t = open(p).read()
m = re.search(r"menuentry '[^']*' --id elementary-aurora72-wip5-trial \{.*?\n\}\n", t, re.S)
assert m, 'wip5 trial entry not found'
e = m.group(0)
e = re.sub(r"menuentry '[^']*'", "menuentry 'elementary OS - TRIAL: Aurora 7.2 wip5, Touch ID (xART guard off)'", e, count=1)
e = e.replace("--id elementary-aurora72-wip5-trial", "--id elementary-aurora72-wip5-xartguard-off-trial")
e, n = re.subn(r"(\n\s*linux /vmlinuz-aurora72-wip5 [^\n]*)", r"\1 apple_sep.xart_guard=0", e, count=1)
assert n == 1
open(p, 'w').write(t[:m.end()] + "\n" + e + t[m.end():])
PY
fi
grub-script-check "$cfg"
echo
echo "Done. To boot the Touch ID entry once:"
echo "  sudo grub-reboot elementary-aurora72-wip5-xartguard-off-trial && sudo reboot"
echo "To undo the entry: sudo cp $dir/custom.cfg.before $cfg"
