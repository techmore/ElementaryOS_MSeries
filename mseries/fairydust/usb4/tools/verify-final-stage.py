#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Verify actual staged archive, module contents, preload path and unique test cmdline."""
import argparse, gzip, hashlib, importlib.util, json, re
from pathlib import Path

def sha(data): return hashlib.sha256(data).hexdigest()

def verify(stage_manifest, repacker):
 manifest=json.loads(stage_manifest.read_text());directory=stage_manifest.parent
 spec=importlib.util.spec_from_file_location('repacker',repacker)
 lib=importlib.util.module_from_spec(spec);spec.loader.exec_module(lib)
 for name,digest in {**manifest['inputs'],**manifest['outputs']}.items():
  if sha(Path(name).read_bytes())!=digest:raise ValueError('changed staged input/output: '+name)
 image=directory/'initramfs-linux-asahi-fairydust-usb4-dpin-controlled.img'
 rows,_=lib.parse(gzip.decompress(image.read_bytes()))
 entries={lib.canonical(n):data for n,_,data in rows}
 report=json.loads((directory/'initramfs-validation.json').read_text())
 for name,digest in report['module_hashes'].items():
  matches=[data for path,data in entries.items() if path.endswith('/'+name)]
  if len(matches)!=1 or sha(matches[0])!=digest:raise ValueError('bad/duplicate archived module: '+name)
 config=entries['config'].decode();init=entries['init'].decode()
 match=re.findall(r'^MODULES="([^"]*)"$',config,re.M)
 modules=['phy_apple_atc','phy_apple_dpin','appledrm','thunderbolt','thunderbolt_apple']
 if len(match)!=1 or match[0].split()[:5]!=modules:raise ValueError('five modules are not first in preload order')
 positions=[init.find(token) for token in ('. /config',"run_hookfunctions 'run_earlyhook'",'modprobe -qab',"run_hookfunctions 'run_hook'")]
 if min(positions)<0 or positions!=sorted(positions):raise ValueError('unexpected init/config/preload/hook execution order')
 configs={path:data.decode() for path,data in entries.items() if '/modprobe.d/' in path and path.endswith('.conf')}
 for path,text in configs.items():
  for line in text.splitlines():
   tokens=line.split('#',1)[0].split()
   if len(tokens)>=2 and tokens[1].replace('-','_') in modules and tokens[0] in ('blacklist','install','remove'):
    raise ValueError('archived module load override: '+path+': '+line)
   if len(tokens)>=2 and tokens[0]=='options' and tokens[1].replace('-','_')=='thunderbolt':
    raise ValueError('unexpected archived Thunderbolt parameter override: '+path+': '+line)
 fragment=(directory/'custom-grub-addition.cfg').read_text()
 linux=re.findall(r'^\s*linux\s+(.+)$',fragment,re.M)
 if len(linux)!=1:raise ValueError('expected one controlled linux command')
 args=linux[0].split()
 expected={'thunderbolt.allow_dp_tunnel':'1','thunderbolt.dprx_bypass':'1','thunderbolt.dprx_timeout':'15000'}
 for key,value in expected.items():
  matches=[arg for arg in args if arg.startswith(key+'=')]
  if matches!=[key+'='+value]:raise ValueError('unsafe duplicate/wrong GRUB parameter: '+key)
 original=(directory/'custom-grub-original.cfg').read_bytes()
 if (directory/'custom-grub-controlled.cfg').read_bytes()!=original+fragment.encode():raise ValueError('original GRUB entries altered')
 result={'status':'PASS: actual final image verified offline','source_revision':manifest['source_revision'],'initramfs_sha256':sha(image.read_bytes()),'all_five_archived_module_hashes_match':True,'ordered_preload_before_udev_coldplug':True,'archived_thunderbolt_option_overrides':False,'unique_test_parameters':expected,'original_grub_entries_preserved':True,'note':'Host modprobe --show-depends inherits current host /proc/cmdline (3600000); that display is not a staged boot option. Actual first-boot /proc/cmdline and /sys/module parameters remain required hardware evidence.'}
 return result

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage-manifest',required=True,type=Path);p.add_argument('--repacker',required=True,type=Path);p.add_argument('--report',type=Path)
 a=p.parse_args();result=verify(a.stage_manifest,a.repacker)
 if a.report:
  with a.report.open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
