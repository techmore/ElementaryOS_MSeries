#!/usr/bin/env bash
# Stage an Aurora 7.2 unified72 kernel (wip5 by default) on the J314S beside the working one, as a
# non-default TRIAL GRUB entry. The persistent default and the shared boot.bin are not touched.
#
# The J314S boots an Arch mkinitcpio initramfs (cryptdevice= and the encrypt + plymouth hooks).
# Never build the new initramfs with initramfs-tools/mkinitramfs: it ignores cryptdevice= and the
# kernel dies before the passphrase prompt (wip5 first try, 2026-10-29). Instead retarget the working
# initramfs with prepare-trial-initrd.py and audit it, which is what this script does.
#
#   sudo bash stage-wip5.sh /path/to/linux-image-elementary-aurora72-wip5_*.deb
# Optional: WORKING=7.2.11-elementary-aurora72-wip4 NEW=7.2.11-elementary-aurora72-wip5 SLUG=aurora72-wip5
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo 'run with sudo' >&2; exit 1; }
deb=${1:?usage: stage-wip5.sh <package.deb>}
here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
aurora=$(cd -- "$here/../.." && pwd)   # mseries/aurora
WORKING=${WORKING:-7.2.11-elementary-aurora72-wip4}
NEW=${NEW:-7.2.11-elementary-aurora72-wip5}
SLUG=${SLUG:-aurora72-wip5}
WORKING_SLUG=${WORKING_SLUG:-${WORKING#*elementary-}}
cfg=/boot/grub/custom.cfg

ts=$(date -u +%Y%m%dT%H%M%SZ)
backup=/var/lib/mseries-kernel-tests/staging/$ts-$SLUG
mkdir -p "$backup"; chmod 700 "$backup"
cp -a "$cfg" /boot/grub/grubenv "$backup/"

dpkg -i "$deb"
depmod -a "$NEW"
install -m 0755 "/usr/lib/modules/$NEW/vmlinuz" "/boot/vmlinuz-$SLUG"

# Retarget the working Arch initramfs: same early archive, hooks and unlock userspace, new modules.
work=$backup/initrd
mkdir -m 700 "$work"
python3 "$aurora/prepare-trial-initrd.py" --baseline "/boot/initrd.img-$WORKING" --module-root /usr \
  --old-version "$WORKING" --new-version "$NEW" --output "$work/initrd.img-$NEW" --report "$work/module-preparation.json"
python3 - "$aurora/audit-trial-initrd.py" "/boot/initrd.img-$WORKING" "$work/initrd.img-$NEW" "/usr/lib/modules/$NEW" <<'PY'
import importlib.util, sys
from pathlib import Path
s = importlib.util.spec_from_file_location('audit', sys.argv[1]); a = importlib.util.module_from_spec(s); s.loader.exec_module(a)
r = a.audit(Path(sys.argv[2]).read_bytes(), Path(sys.argv[3]).read_bytes(), Path(sys.argv[4]))
for k in ('early_prefix_unchanged', 'nonmodule_entries_unchanged', 'module_bytes_match_candidate_tree', 'dependency_files_present'):
    assert r[k] is True, k
print('initramfs audit passed:', r['verified_module_count'], 'modules')
PY
install -m 0755 "$work/initrd.img-$NEW" "/boot/initrd.img-$NEW"

if ! grep -q "elementary-$SLUG-trial" "$cfg"; then
  python3 - "$cfg" "$WORKING_SLUG" "$SLUG" "$WORKING" "$NEW" <<'PY'
import re, sys
p, ws, ns, wv, nv = sys.argv[1:]
t = open(p).read()
m = re.search(r"menuentry '[^']*' --id elementary-" + re.escape(ws) + r"-trial \{.*?\n\}\n", t, re.S)
assert m, 'working trial entry not found'
e = re.sub(r"menuentry '[^']*'", f"menuentry 'elementary OS - TRIAL: Aurora 7.2 {ns.split('-')[-1]}'", m.group(0), count=1)
e = e.replace(f"elementary-{ws}-trial", f"elementary-{ns}-trial").replace(f"/vmlinuz-{ws}", f"/vmlinuz-{ns}").replace(f"initrd.img-{wv}", f"initrd.img-{nv}")
assert ws not in e
open(p, 'w').write(t[:m.end()] + "\n" + e + t[m.end():])
PY
fi
grub-script-check "$cfg"
echo "Staged $NEW (backup $backup). Default unchanged. Boot it once with:"
echo "  sudo grub-reboot elementary-$SLUG-trial && sudo reboot"
