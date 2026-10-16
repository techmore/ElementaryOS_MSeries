#!/usr/bin/env bash
# Owner-run installer for the batched DP-IN / DCP-source bridge test boot.
#
#   bash install-dpin-batch.sh --bundle DIR                 # DRY RUN (default): checks + plan, writes nothing
#   sudo bash install-dpin-batch.sh --bundle DIR --apply    # performs every step below
#
# What --apply does, in this order (see POST-REBOOT-CHECKLIST.md):
#   1. verify the bundle against its manifests (SHA-256, vermagic == bundle kernelrelease)
#   2. save a rollback directory (current modules, module metadata, boot.bin, initramfs, custom.cfg)
#   3. install the five modules under /usr/lib/modules/<kv>/ and run depmod
#   4. write a NEW initramfs (never overwrites the current one) via tools/repack-dpin-initramfs.py
#   5. append ONE new GRUB menuentry (bypass armed, short timeout); the default entry is not changed
#   6. replace /boot/m1n1/boot.bin LAST with the bundle's boot-dpin.bin (affects every entry)
# It never reboots, never edits the default boot entry and never runs grub-reboot.
#
# KNOWN SIDE EFFECT (decide before --apply): step 3 changes /usr/lib/modules/<kv>, which the
# existing 'elementary-usb4-dptunnel' entry shares by kernel version. That entry keeps its OLD
# initramfs (old appledrm/phy-apple-atc) but would then load the NEW thunderbolt_apple, which
# needs the new appledrm symbols, so USB4 (dock USB/Ethernet) would not come up on it. It still
# boots. Other kernels (stock, non-dptunnel fairydust-usb4) keep their own module trees but share
# boot.bin, so they get the new device tree (extra DP-IN nodes they have no driver for).
# Rollback restores everything from the saved directory.
# Written 2026-10-16 by Claude; NOT YET RUN. Review before use; the bundle must be frozen first.
# SUPERSEDED for the current controlled test: root modules must remain intact.
# See CONTROLLED-TEST.md and tools/apply-controlled-test.py. Legacy dry-run
# retained for comparison; --apply is disabled below to avoid mixing plans.
set -euo pipefail

here=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
bundle=; apply=0; timeout_ms=12000
while (($#)); do
  case $1 in
    --bundle) bundle=${2:?}; shift 2;;
    --apply) apply=1; shift;;
    --dprx-timeout-ms) timeout_ms=${2:?}; shift 2;;
    -h|--help) sed -n '2,19p' "$0"; exit 0;;
    *) echo "unknown argument: $1" >&2; exit 2;;
  esac
done
if ((apply)); then
  echo 'Superseded: use the isolated-initramfs manifest installer in CONTROLLED-TEST.md.' >&2
  exit 2
fi
[[ -n $bundle && -d $bundle ]] || { echo "need --bundle DIR (the 'deployment' directory)" >&2; exit 2; }
bundle=$(cd -- "$bundle" && pwd)
((apply == 0)) || [[ $EUID -eq 0 ]] || { echo "--apply needs root (sudo)" >&2; exit 1; }

say() { printf '%s\n' "$*"; }
run() { if ((apply)); then "$@"; else say "  [dry-run] $*"; fi; }
die() { echo "STOP: $*" >&2; exit 1; }

mods=(phy-apple-atc phy-apple-dpin appledrm thunderbolt thunderbolt_apple)
for f in "${mods[@]/%/.ko}" boot-dpin.bin module-validation.json boot-validation.json; do
  [[ -f $bundle/$f ]] || die "bundle is missing $f"
done

# ---- 1. verify -------------------------------------------------------------
kv=$(python3 -I -c 'import json,sys;print(json.load(open(sys.argv[1]))["kernelrelease"])' "$bundle/module-validation.json")
[[ $kv == "$(uname -r)" ]] || die "bundle is for $kv but the running kernel is $(uname -r)"
python3 -I - "$bundle" <<'PY'
import hashlib, json, pathlib, sys
b = pathlib.Path(sys.argv[1])
mv = json.load(open(b / 'module-validation.json'))
for m in mv['modules']:
    got = hashlib.sha256((b / m['file']).read_bytes()).hexdigest()
    assert got == m['sha256'], f"{m['file']}: sha256 {got} != manifest {m['sha256']}"
bv = json.load(open(b / 'boot-validation.json'))
got = hashlib.sha256((b / 'boot-dpin.bin').read_bytes()).hexdigest()
assert got == bv['output_sha256'], f"boot-dpin.bin sha256 {got} != manifest {bv['output_sha256']}"
assert bv.get('prefix_suffix_unchanged') is True
print(f"verified {len(mv['modules'])} modules and boot-dpin.bin against manifests")
PY
for m in "${mods[@]}"; do
  v=$(modinfo -F vermagic "$bundle/$m.ko" | awk '{print $1}')
  [[ $v == "$kv" ]] || die "$m.ko vermagic $v != $kv"
done
moddir=/usr/lib/modules/$kv
[[ -d $moddir && ! -e $moddir/$kv ]] || die "$moddir missing, or nested $kv/$kv present"
src_boot=/boot/m1n1/boot.bin
[[ -f $src_boot ]] || die "$src_boot missing"
ls /boot/m1n1/boot.bin.KNOWN-GOOD-* >/dev/null 2>&1 || die "no KNOWN-GOOD boot.bin copies in /boot/m1n1 (RECOVERY.md)"
old_initrd=/boot/initramfs-linux-asahi-fairydust-usb4-dptunnel.img
new_initrd=/boot/initramfs-linux-asahi-fairydust-usb4-dptunnel-dpin.img
[[ -f $old_initrd ]] || die "$old_initrd missing"
[[ ! -e $new_initrd ]] || die "$new_initrd already exists; refusing to overwrite"
grep -q "id elementary-usb4-dpin" /boot/grub/custom.cfg && die "GRUB entry elementary-usb4-dpin already present"
say "checks passed for $kv"
say "NOTE: after --apply the old elementary-usb4-dptunnel entry will not bring up USB4 (shared module tree); use the new entry or roll back."

# ---- 2. rollback -----------------------------------------------------------
rb=/root/dpin-rollback-$(date +%Y%m%d-%H%M%S)
say "rollback directory: $rb"
run mkdir -p "$rb/modules"
for m in phy-apple-atc appledrm thunderbolt thunderbolt_apple; do
  p=$(find "$moddir/kernel" -name "$m.ko" | head -1)
  [[ -n $p ]] && run cp -a "$p" "$rb/modules/$m.ko"
done
run cp -a "$moddir"/modules.* "$rb/modules/"
run cp -a "$src_boot" "$rb/boot.bin"
run cp -a "$old_initrd" "$rb/"
run cp -a /boot/grub/custom.cfg "$rb/custom.cfg"

# ---- 3. modules -----------------------------------------------------------
atc_dir=$(dirname "$(find "$moddir/kernel" -name phy-apple-atc.ko | head -1)")
for m in phy-apple-atc phy-apple-dpin; do run install -m644 "$bundle/$m.ko" "$atc_dir/$m.ko"; done
run install -m644 "$bundle/appledrm.ko" "$(dirname "$(find "$moddir/kernel" -name appledrm.ko | head -1)")/appledrm.ko"
for m in thunderbolt thunderbolt_apple; do
  run install -m644 "$bundle/$m.ko" "$(dirname "$(find "$moddir/kernel" -name "$m.ko" | head -1)")/$m.ko"
done
run depmod -a "$kv"

# ---- 4. initramfs (new file) -----------------------------------------------
if ((apply)); then
  tmp=$(mktemp -d /var/tmp/dpin-initrd.XXXXXX); trap 'rm -rf "$tmp"' EXIT
  python3 -I - "$old_initrd" "$moddir" "$kv" "$tmp/mapping.json" "$bundle" "$here/tools" <<'PY'
import gzip, json, pathlib, sys
old, moddir, kv, out, bundle, tools = sys.argv[1:]
sys.path.insert(0, tools)
import importlib.util
spec = importlib.util.spec_from_file_location('repack', pathlib.Path(tools) / 'repack-dpin-initramfs.py')
r = importlib.util.module_from_spec(spec); spec.loader.exec_module(r)
rows, _ = r.parse(gzip.decompress(pathlib.Path(old).read_bytes()))
names = {r.canonical(n) for n, _, _ in rows}
base = f'usr/lib/modules/{kv}'
mapping = {}
for n in sorted(names):                      # regenerated depmod metadata already in the image
    if n.startswith(f'{base}/modules.') and pathlib.Path('/' + n).is_file():
        mapping[n] = '/' + n
for ko, rel in (('appledrm', 'kernel/drivers/gpu/drm/apple'), ('phy-apple-atc', 'kernel/drivers/phy/apple'),
                ('phy-apple-dpin', 'kernel/drivers/phy/apple')):
    mapping[f'{base}/{rel}/{ko}.ko'] = f'{bundle}/{ko}.ko'
json.dump(mapping, open(out, 'w'), indent=2)
print(json.dumps(mapping, indent=2))
PY
  python3 -I "$here/tools/repack-dpin-initramfs.py" --input "$old_initrd" --mapping "$tmp/mapping.json" \
    --output "$new_initrd" --report "$rb/initramfs-report.json"
else
  say "  [dry-run] repack $old_initrd -> $new_initrd (appledrm, phy-apple-atc, phy-apple-dpin + modules.* metadata)"
fi

# ---- 5. GRUB entry (additional; default unchanged) ---------------------------
cmd=$(awk "/id elementary-usb4-dptunnel/{f=1} f&&/^[[:space:]]*linux /{print; exit}" /boot/grub/custom.cfg)
[[ -n $cmd ]] || die "could not read the elementary-usb4-dptunnel linux line from custom.cfg"
cmd=$(sed -E 's/ thunderbolt\.dprx_timeout=[0-9]+//; s/ thunderbolt\.dprx_bypass=[0-9]+//' <<<"$cmd")
cmd="$cmd thunderbolt.dprx_bypass=1 thunderbolt.dprx_timeout=$timeout_ms"
entry=$(cat <<EOF

menuentry 'elementary OS (M-series, USB4 DP-IN bridge test, bypass armed)' --id elementary-usb4-dpin {
    search --no-floppy --fs-uuid --set=root D893-79A4
$cmd
    initrd /$(basename "$new_initrd")
}
EOF
)
say "GRUB entry to append:"; say "$entry"
if ((apply)); then printf '%s\n' "$entry" >>/boot/grub/custom.cfg; fi

# ---- 6. boot.bin (affects every entry; last) ---------------------------------
run install -m755 "$bundle/boot-dpin.bin" "$src_boot"

say
say "$( ((apply)) && echo DONE || echo 'DRY RUN COMPLETE: nothing was written')"
say "Next (owner): choose the new entry once at the GRUB menu; run POST-REBOOT-CHECKLIST.md section D."
say "Rollback: restore from $rb (boot.bin first; see RECOVERY.md if the machine does not reach GRUB)."
