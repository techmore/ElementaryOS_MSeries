#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Hash-guarded plan/apply/rollback; never changes root modules or arms a reboot."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

ENTRY = 'elementary-usb4-dpin-controlled'
IMAGE = 'initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img'

def sha(path):
 return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def check(path, expected):
 p = Path(path)
 if not p.is_file() or p.is_symlink() or sha(p) != expected:
  raise ValueError('missing/changed/symlink input: ' + str(p))

def jsonwrite(path, data):
 with Path(path).open('x') as f:
  json.dump(data, f, indent=2)
  f.write('\n')
  f.flush()
  os.fsync(f.fileno())

def atomic_copy(source, destination, mode):
 destination = Path(destination)
 if destination.is_symlink():
  raise ValueError('symlink destination refused')
 fd, temp = tempfile.mkstemp(prefix='.dpin-controlled-', dir=destination.parent)
 try:
  with os.fdopen(fd, 'wb') as f, Path(source).open('rb') as src:
   shutil.copyfileobj(src, f)
   os.fchmod(f.fileno(), mode)
   f.flush()
   os.fsync(f.fileno())
  os.replace(temp, destination)
  dfd = os.open(destination.parent, os.O_DIRECTORY)
  try: os.fsync(dfd)
  finally: os.close(dfd)
 finally:
  Path(temp).unlink(missing_ok=True)

def plan(a):
 if os.geteuid() == 0:
  raise ValueError('run plan unprivileged; apply/rollback alone require root')
 stage_path = a.stage_manifest.resolve()
 stage = json.loads(stage_path.read_text())
 if stage['entry_id'] != ENTRY or not stage['root_modules_unchanged'] or not stage['original_grub_entries_unchanged']:
  raise ValueError('stage does not preserve fallback')
 for path, digest in {**stage['inputs'], **stage['outputs']}.items():
  check(path, digest)
 custom = Path('/boot/grub/custom.cfg')
 boot = Path('/boot/m1n1/boot.bin')
 image = Path('/boot') / IMAGE
 new_custom = stage_path.parent / 'custom-grub-controlled.cfg'
 new_image = stage_path.parent / IMAGE
 original_custom = stage_path.parent / 'custom-grub-original.cfg'
 fragment = stage_path.parent / 'custom-grub-addition.cfg'
 if original_custom.read_bytes() != custom.read_bytes() or new_custom.read_bytes() != custom.read_bytes() + fragment.read_bytes():
  raise ValueError('original entries changed; new config must be an exact append')
 if image.exists() or image.is_symlink():
  raise ValueError('new test initramfs name collides with existing file')
 subprocess.run(['grub-script-check', str(new_custom)], check=True)
 report = json.loads(a.boot_report.read_text())
 if report.get('prefix_suffix_unchanged') is not True:
  raise ValueError('boot payload preservation check missing/failed')
 if report.get('boot_sha256') != sha(boot) or report.get('output_sha256') != sha(a.boot_candidate):
  raise ValueError('boot report input/output hashes do not match actual files')
 # Compatibility review is mandatory, deliberately separate from payload formatting.
 compatibility = json.loads(a.compatibility_record.read_text())
 if compatibility.get('fallback_compatible') is not True or compatibility.get('boot_candidate_sha256') != sha(a.boot_candidate):
  raise ValueError('reviewed fallback compatibility record must match final boot candidate')
 if compatibility.get('original_dcp_phys_preserved') is not True:
  raise ValueError('fallback DCP PHY preservation not recorded')
 if compatibility.get('root_modules_untouched') is not True:
  raise ValueError('fallback root modules preservation not recorded')
 if sha(a.boot_candidate) == sha(boot):
  raise ValueError('boot candidate identical to original; unexpected empty deployment')
 rollback = a.rollback_dir.resolve()
 if rollback.exists() or rollback == Path('/boot') or Path('/boot') in rollback.parents:
  raise ValueError('rollback directory must be fresh and outside ESP')
 manifest = {
  'status': 'planned; no system writes; reboot must be separately armed',
  'stage_manifest': str(stage_path), 'stage_manifest_sha256': sha(stage_path),
  'compatibility_record': str(a.compatibility_record.resolve()), 'compatibility_sha256': sha(a.compatibility_record),
  'boot_report': str(a.boot_report.resolve()), 'boot_report_sha256': sha(a.boot_report),
  'rollback_dir': str(rollback), 'entry_id': ENTRY,
  'operations': [
   {'target': str(image), 'original_sha256': None, 'candidate': str(new_image.resolve()), 'candidate_sha256': sha(new_image), 'mode': 0o644},
   {'target': str(custom), 'original_sha256': sha(custom), 'candidate': str(new_custom.resolve()), 'candidate_sha256': sha(new_custom), 'mode': stat.S_IMODE(custom.stat().st_mode)},
   {'target': str(boot), 'original_sha256': sha(boot), 'candidate': str(a.boot_candidate.resolve()), 'candidate_sha256': sha(a.boot_candidate), 'mode': stat.S_IMODE(boot.stat().st_mode)},
  ],
  'grubenv_sha256': sha('/boot/grub/grubenv'),
  'default_entry_unchanged': True, 'root_modules_unchanged': True,
  'next_step_after_apply': 'Separately review and arm one-shot GRUB entry; this installer does not run grub-reboot or reboot.',
 }
 jsonwrite(a.output, manifest)
 print(json.dumps({'install_manifest': str(a.output.resolve()), 'manifest_sha256': sha(a.output), 'status': manifest['status']}, indent=2))

def load_manifest(a):
 check(a.manifest, a.expect_manifest_sha256)
 m = json.loads(a.manifest.read_text())
 if m['entry_id'] != ENTRY or not m['root_modules_unchanged'] or not m['default_entry_unchanged']:
  raise ValueError('unsafe manifest')
 expected_targets = ['/boot/' + IMAGE, '/boot/grub/custom.cfg', '/boot/m1n1/boot.bin']
 if [o['target'] for o in m['operations']] != expected_targets:
  raise ValueError('unexpected target set or order')
 if os.geteuid() != 0:
  raise ValueError('apply/rollback require root; no sudo performed automatically')
 return m

def apply(a):
 m = load_manifest(a)
 check(m['stage_manifest'], m['stage_manifest_sha256'])
 stage = json.loads(Path(m['stage_manifest']).read_text())
 for path, digest in {**stage['inputs'], **stage['outputs']}.items(): check(path, digest)
 check(m['compatibility_record'], m['compatibility_sha256'])
 check(m['boot_report'], m['boot_report_sha256'])
 check('/boot/grub/grubenv', m['grubenv_sha256'])
 rollback = Path(m['rollback_dir'])
 if rollback.exists():
  raise ValueError('rollback directory already exists; inspect partial apply before proceeding')
 for op in m['operations']:
  check(op['candidate'], op['candidate_sha256'])
  target = Path(op['target'])
  if op['original_sha256'] is None:
   if target.exists() or target.is_symlink(): raise ValueError('target collision')
  else:
   check(target, op['original_sha256'])
 rollback.mkdir(parents=True, mode=0o700)
 jsonwrite(rollback / 'install-manifest.json', m)
 for index, op in enumerate(m['operations']):
  if op['original_sha256'] is not None:
   backup = rollback / ('original-' + str(index))
   atomic_copy(op['target'], backup, 0o600)
   check(backup, op['original_sha256'])
 atomic_copy('/boot/grub/grubenv', rollback / 'grubenv-before', 0o600)
 # Exact order: unique image, append-only config, global boot payload last.
 for index, op in enumerate(m['operations']):
  atomic_copy(op['candidate'], op['target'], op['mode'])
  check(op['target'], op['candidate_sha256'])
  jsonwrite(rollback / ('applied-' + str(index) + '.json'), op)
 check('/boot/grub/grubenv', m['grubenv_sha256'])
 print(json.dumps({'status': 'installed only; no reboot armed', 'rollback_dir': str(rollback), 'next_step': m['next_step_after_apply']}, indent=2))

def rollback(a):
 m = load_manifest(a)
 directory = Path(m['rollback_dir'])
 if json.loads((directory / 'install-manifest.json').read_text()) != m:
  raise ValueError('rollback manifest mismatch')
 # Refuse to touch any target changed by another writer, including partial applies.
 for index, op in enumerate(m['operations']):
  target = Path(op['target'])
  if target.is_symlink(): raise ValueError('symlink target refused')
  if op['original_sha256'] is None:
   if target.exists(): check(target, op['candidate_sha256'])
  else:
   if not target.is_file() or sha(target) not in (op['original_sha256'], op['candidate_sha256']):
    raise ValueError('rollback target changed by another writer: ' + str(target))
   check(directory / ('original-' + str(index)), op['original_sha256'])
 # Restore global boot payload first, then original GRUB bytes, then remove test image.
 for index in (2, 1):
  op = m['operations'][index]
  if sha(op['target']) == op['candidate_sha256']:
   atomic_copy(directory / ('original-' + str(index)), op['target'], op['mode'])
  check(op['target'], op['original_sha256'])
 image = Path(m['operations'][0]['target'])
 image.unlink(missing_ok=True)
 dfd = os.open(image.parent, os.O_DIRECTORY)
 try: os.fsync(dfd)
 finally: os.close(dfd)
 print(json.dumps({'status': 'original boot/config restored; test image removed', 'grubenv_untouched': True, 'note': 'If a separate one-shot was armed, coordinator must clear it separately before reboot.'}, indent=2))

def main():
 p = argparse.ArgumentParser(description=__doc__)
 sub = p.add_subparsers(dest='mode', required=True)
 q = sub.add_parser('plan')
 for arg in ('stage-manifest', 'boot-candidate', 'boot-report', 'compatibility-record', 'rollback-dir', 'output'):
  q.add_argument('--' + arg, type=Path, required=True)
 q.set_defaults(func=plan)
 for mode in ('apply', 'rollback'):
  q = sub.add_parser(mode)
  q.add_argument('--manifest', type=Path, required=True)
  q.add_argument('--expect-manifest-sha256', required=True)
  q.set_defaults(func=apply if mode == 'apply' else rollback)
 a = p.parse_args()
 a.func(a)
if __name__ == '__main__': main()
