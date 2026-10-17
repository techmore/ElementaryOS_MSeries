#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Regression cases for real newc formats and scratch-only installer safeguards."""
import contextlib,gzip,importlib.util,io,json,stat,tempfile,types
from pathlib import Path
BASE=Path(__file__).resolve().parent

def load(name,file):
 spec=importlib.util.spec_from_file_location(name,BASE/file);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def main():
 rep=load('rep','repack-dpin-initramfs.py');install=load('installer','apply-controlled-test.py');stage=load('stage','stage-controlled-test.py')
 with tempfile.TemporaryDirectory() as tmp:
  d=Path(tmp);install.GRUBENV=d/'grubenv';install.GRUBENV.write_bytes(b'unchanged grub environment');replace=d/'replace';replace.write_bytes(b'new');trailer=[0,0,0,0,1,0,0,0,0,0,0,0,0]
  def archive(nlink,shared=False):
   v=[1,stat.S_IFREG|0o644,0,0,nlink,0,3,0,1,0,0,0,0];rows=[('a',v,b'old')]
   if shared:rows.append(('b',v.copy(),b'old'))
   return gzip.compress(rep.encode(rows,trailer))
  for nlink in (0,1):rep.repack(archive(nlink),{'a':str(replace)})
  for nlink,shared in ((2,False),(0,True),(1,True)):
   try:rep.repack(archive(nlink,shared),{'a':str(replace)})
   except ValueError:pass
   else:raise AssertionError('shared/hardlinked replacement accepted')
  print('PASS: real mkinitcpio nlink0/ordinary nlink1; hardlink/shared inode refusal')
  original="menuentry 'old' --id elementary-usb4-dptunnel {\n    linux /vmlinuz-original root=x thunderbolt.dprx_timeout=3600000 thunderbolt.dprx_bypass=0\n    initrd /old.img\n}\n"
  fragment,kernel=stage.grub_fragment(original)
  assert kernel=='/vmlinuz-original' and '3600000' not in fragment and 'dprx_bypass=0' not in fragment
  for token in ('thunderbolt.dprx_bypass=1','thunderbolt.dprx_timeout=15000'):assert fragment.count(token)==1
  try:stage.grub_fragment(original+fragment)
  except ValueError:pass
  else:raise AssertionError('GRUB entry collision accepted')
  print('PASS: separate GRUB clean parameters and duplicate-entry refusal')
  rollback=d/'rollback';staged=d/'stage.json';compat=d/'compat.json';report=d/'report.json'
  staged.write_text(json.dumps({'inputs':{},'outputs':{}}));compat.write_text('{}');report.write_text('{}');ops=[]
  for i in range(3):
   target=d/f'target{i}';candidate=d/f'candidate{i}';candidate.write_bytes(f'new{i}'.encode())
   if i:target.write_bytes(f'old{i}'.encode())
   ops.append({'target':str(target),'original_sha256':install.sha(target) if i else None,'candidate':str(candidate),'candidate_sha256':install.sha(candidate),'mode':0o644})
  manifest={'stage_manifest':str(staged),'stage_manifest_sha256':install.sha(staged),'compatibility_record':str(compat),'compatibility_sha256':install.sha(compat),'boot_report':str(report),'boot_report_sha256':install.sha(report),'grubenv_sha256':install.sha(install.GRUBENV),'operations':ops,'rollback_dir':str(rollback),'next_step_after_apply':'test'}
  # Redirect the production installer to throwaway targets; root/real-path guard
  # intentionally bypassed only in this fixture. No host boot files are accessed.
  install.load_manifest=lambda args:manifest
  with contextlib.redirect_stdout(io.StringIO()):install.apply(types.SimpleNamespace())
  for op in ops:assert install.sha(op['target'])==op['candidate_sha256']
  Path(ops[1]['target']).write_bytes(b'external writer')
  try:install.rollback(types.SimpleNamespace())
  except ValueError:pass
  else:raise AssertionError('rollback overwrote external writer')
  assert install.sha(ops[2]['target'])==ops[2]['candidate_sha256']
  Path(ops[1]['target']).write_bytes(Path(ops[1]['candidate']).read_bytes())
  with contextlib.redirect_stdout(io.StringIO()):install.rollback(types.SimpleNamespace())
  assert not Path(ops[0]['target']).exists()
  for op in ops[1:]:assert install.sha(op['target'])==op['original_sha256']
  print('PASS: scratch apply, modified-target rejection, exact rollback; no live writes')
if __name__=='__main__':main()
