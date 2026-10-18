#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Stage a hash-frozen initramfs and GRUB addition. Never changes boot/root files."""
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

FILES = {
 'phy-apple-atc.ko': 'kernel/drivers/phy/apple/phy-apple-atc.ko',
 'phy-apple-dpin.ko': 'kernel/drivers/phy/apple/phy-apple-dpin.ko',
 'appledrm.ko': 'kernel/drivers/gpu/drm/apple/appledrm.ko',
 'thunderbolt.ko': 'kernel/drivers/thunderbolt/thunderbolt.ko',
 'thunderbolt_apple.ko': 'kernel/drivers/thunderbolt/thunderbolt_apple.ko',
}
ENTRY = 'elementary-usb4-dpin-controlled'
IMAGE = 'initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img'

def digest(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def grub_fragment(original):
 pattern = r"(?ms)^menuentry [^\n]*--id elementary-usb4-dptunnel\s*\{\n.*?^\}"
 matches = re.findall(pattern, original)
 if len(matches) != 1:
  raise ValueError('expected exactly one original dptunnel GRUB entry')
 if ENTRY in original or IMAGE in original:
  raise ValueError('controlled entry/image already present')
 block = matches[0]
 block = re.sub(r"^menuentry [^\n]+", "menuentry 'elementary OS (DP-IN controlled test)' --id " + ENTRY + ' {', block, count=1)
 linux = re.findall(r'^\s*linux\s+(.+)$', block, re.M)
 initrd = re.findall(r'^\s*initrd\s+(.+)$', block, re.M)
 if len(linux) != 1 or len(initrd) != 1:
  raise ValueError('expected one linux/initrd command in original entry')
 args = linux[0].split()
 if not args[0].startswith('/vmlinuz-'):
  raise ValueError('unexpected kernel pathname')
 args = [x for x in args if not x.startswith(('thunderbolt.allow_dp_tunnel=', 'thunderbolt.dprx_bypass=', 'thunderbolt.dprx_timeout='))]
 args.extend(['thunderbolt.allow_dp_tunnel=1', 'thunderbolt.dprx_bypass=1', 'thunderbolt.dprx_timeout=15000'])
 block = re.sub(r'^\s*linux\s+.*$', '    linux ' + ' '.join(args), block, count=1, flags=re.M)
 block = re.sub(r'^\s*initrd\s+.*$', '    initrd /' + IMAGE, block, count=1, flags=re.M)
 return '\n\n' + block + '\n', args[0]

def main():
 p = argparse.ArgumentParser(description=__doc__)
 p.add_argument('--bundle', required=True, type=Path)
 p.add_argument('--validation', required=True, type=Path)
 p.add_argument('--input-initramfs', required=True, type=Path)
 p.add_argument('--custom-grub', required=True, type=Path)
 p.add_argument('--root-modules', required=True, type=Path)
 p.add_argument('--repacker', required=True, type=Path)
 p.add_argument('--output', required=True, type=Path)
 p.add_argument('--source-revision', required=True, help='frozen reviewed source identifier')
 a = p.parse_args()
 if os.geteuid() == 0:
  raise ValueError('staging must run unprivileged')
 output = a.output.resolve()
 if output == Path('/boot') or Path('/boot') in output.parents or Path('/usr/lib/modules') in output.parents:
  raise ValueError('output must be outside system boot/module paths')
 validation = json.loads(a.validation.read_text())
 kv = validation['kernelrelease']
 if kv != a.root_modules.name or '/' in kv or kv != subprocess.check_output(['uname', '-r'], text=True).strip():
  raise ValueError('validation, module tree and running kernel release differ')
 records = {m['file']: m for m in validation['modules']}
 if set(records) != set(FILES):
  raise ValueError('exactly five validated module files required')
 for name in FILES:
  if digest(a.bundle / name) != records[name]['sha256']:
   raise ValueError('stale validation/bundle: ' + name)
  if records[name]['missing_exports']:
   raise ValueError('unresolved module exports: ' + name)
  if records[name]['module_init_cleanup_offsets'] != ['0000000000000130', '00000000000004a8']:
   raise ValueError('wrong module ABI layout: ' + name)
 spec = importlib.util.spec_from_file_location('repack_dpin', a.repacker)
 repack = importlib.util.module_from_spec(spec)
 spec.loader.exec_module(repack)
 original = a.input_initramfs.read_bytes()
 rows, _ = repack.parse(gzip.decompress(original))
 entries = {repack.canonical(n): (v, data) for n, v, data in rows}
 config = entries.get('config')
 if config is None or not stat.S_ISREG(config[0][1]):
  raise ValueError('expected regular mkinitcpio config entry')
 config_text = config[1].decode()
 module_match = re.findall(r'^MODULES="([^"]*)"$', config_text, re.M)
 if len(module_match) != 1:
  raise ValueError('expected one simple MODULES declaration')
 old_modules = module_match[0].split()
 preload = ['phy_apple_atc', 'phy_apple_dpin', 'appledrm', 'thunderbolt', 'thunderbolt_apple']
 all_modules = [*preload, *(m for m in old_modules if m not in preload)]
 config_text = re.sub(r'^MODULES="[^"]*"$', 'MODULES="' + ' '.join(all_modules) + '"', config_text, count=1, flags=re.M)
 fragment, kernel_path = grub_fragment(a.custom_grub.read_text())
 kernel = a.custom_grub.parent.parent / kernel_path.lstrip('/')
 if not kernel.is_file():
  raise ValueError('existing kernel named in GRUB entry is missing')
 output.mkdir(parents=True, exist_ok=False)
 stage = output / 'depmod-root'
 module_tree = stage / 'lib/modules' / kv
 module_tree.mkdir(parents=True)
 prefix = 'usr/lib/modules/' + kv + '/'
 for name, (values, data) in entries.items():
  if name.startswith(prefix) and stat.S_ISREG(values[1]) and not name[len(prefix):].startswith('modules.'):
   target = module_tree / name[len(prefix):]
   target.parent.mkdir(parents=True, exist_ok=True)
   target.write_bytes(data)
 for name, rel in FILES.items():
  target = module_tree / rel
  target.parent.mkdir(parents=True, exist_ok=True)
  shutil.copyfile(a.bundle / name, target)
 # Builtin data describe the unchanged kernel, not the changed module subset.
 for name in ('modules.builtin', 'modules.builtin.modinfo'):
  shutil.copyfile(a.root_modules / name, module_tree / name)
 # A subset order suppresses bogus references to absent rootfs modules.
 old_order = (a.root_modules / 'modules.order').read_text().splitlines()
 present = {str(path.relative_to(module_tree)) for path in module_tree.rglob('*.ko')}
 order = [path for path in old_order if path in present]
 order.extend(sorted(present - set(order)))
 (module_tree / 'modules.order').write_text('\n'.join(order) + '\n')
 result = subprocess.run(['depmod', '-b', str(stage), kv], capture_output=True, text=True)
 (output / 'depmod.log').write_text(result.stdout + result.stderr)
 if result.returncode or result.stderr.strip():
  raise ValueError('depmod returned an error or diagnostic; inspect depmod.log')
 replacement = {prefix + rel: str(module_tree / rel) for rel in FILES.values()}
 for meta in module_tree.glob('modules.*'):
  replacement[prefix + meta.name] = str(meta)
 config_path = output / 'config'
 config_path.write_text(config_text)
 replacement['config'] = str(config_path)
 packed, report = repack.repack(original, replacement)
 out_image = output / IMAGE
 out_image.write_bytes(packed)
 after_rows, _ = repack.parse(gzip.decompress(packed))
 after = {repack.canonical(n): data for n, _, data in after_rows}
 for name, rel in FILES.items():
  if hashlib.sha256(after[prefix + rel]).hexdigest() != records[name]['sha256']:
   raise ValueError('staged module hash mismatch: ' + name)
 # Use the actual kmod resolver against precisely the staged module subset.
 resolutions = {}
 for module in preload:
  r = subprocess.run(['modprobe', '-d', str(stage), '-S', kv, '--show-depends', module], capture_output=True, text=True)
  if r.returncode or r.stderr.strip():
   raise ValueError('unresolved staged load dependencies: ' + module + ': ' + r.stderr)
  resolutions[module] = r.stdout.strip().splitlines()
 (output / 'custom-grub-addition.cfg').write_text(fragment)
 custom_final = output / 'custom-grub-controlled.cfg'
 custom_final.write_text(a.custom_grub.read_text() + fragment)
 shutil.copyfile(a.custom_grub, output / 'custom-grub-original.cfg')
 report.update({'module_hashes': {name: records[name]['sha256'] for name in FILES}, 'module_preload_order': preload, 'modprobe_show_depends': resolutions, 'modprobe_note': 'Dependency resolver runs on the host and displays the current host cmdline options; final 15000 ms/bypass parameters are validated separately in the new GRUB fragment.'})
 (output / 'initramfs-validation.json').write_text(json.dumps(report, indent=2) + '\n')
 manifest = {
  'status': 'prepared only; deployment blocked until fallback DT compatibility reviewed',
  'source_revision': a.source_revision, 'kernelrelease': kv, 'entry_id': ENTRY,
  'root_modules_unchanged': True, 'original_initramfs_unchanged': True,
  'original_grub_entries_unchanged': True, 'default_grub_entry_unchanged': True,
  'command_line': {'thunderbolt.allow_dp_tunnel': 1, 'thunderbolt.dprx_bypass': 1, 'thunderbolt.dprx_timeout': 15000},
  'inputs': {str(path.resolve()): digest(path) for path in [a.validation, a.input_initramfs, a.custom_grub, kernel, a.repacker, a.root_modules / 'modules.builtin', a.root_modules / 'modules.builtin.modinfo', *[a.bundle / n for n in FILES]]},
  'outputs': {str(path.resolve()): digest(path) for path in [out_image, custom_final, output / 'custom-grub-addition.cfg', output / 'initramfs-validation.json']},
  'install_plan': [
   'Recheck all input/output SHA-256s and reviewed fallback compatibility against final source/DT hashes.',
   'Back up current boot.bin/custom.cfg/grubenv to a durable rollback directory.',
   'Copy new initramfs under its unique name; leave original image and root modules untouched.',
   'Append separate GRUB entry, preserving original bytes/default; validate with grub-script-check.',
   'Write reviewed fallback-compatible boot.bin last, with exact original/candidate hashes.',
   'Set grub-reboot elementary-usb4-dpin-controlled; verify next_entry; one controlled reboot.',
  ],
  'rollback_plan': [
   'Clear only the controlled one-shot next_entry if armed.',
   'Restore original boot.bin and custom.cfg from verified pre-write copies.',
   'Original root modules/initramfs/default entry were never modified.',
   'For boot failure use documented macOS ESP recovery to restore known-good boot.bin.',
  ],
  'remaining_blockers': ['Fallback-compatible DT payload and reviewed rollback installer are coordinator-owned.', 'No real firmware timing/module load qualification until first controlled boot.'],
 }
 (output / 'stage-manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
 print(json.dumps({'status': 'scratch stage prepared', 'manifest': str(output / 'stage-manifest.json'), 'initramfs_sha256': digest(out_image), 'no_system_writes': True}, indent=2))

if __name__ == '__main__':
 main()
