#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only OR MIT
"""Read-only postboot collector; writes a fresh local output directory only."""
import argparse,hashlib,json,os,re,struct,subprocess,time
from pathlib import Path

def run(argv):
 try:
  p=subprocess.run(argv,capture_output=True,text=True,timeout=30)
  return {'command':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
 except (OSError,subprocess.TimeoutExpired) as e:return {'command':argv,'error':str(e)}

def read(path):
 try:return Path(path).read_text().strip()
 except OSError as e:return 'ERROR: '+str(e)

def module_identity(filename, manifest, sysroot=Path('/sys')):
 name=filename[:-3].replace('-','_')
 item={'module':name,'matches_frozen_bundle':False}
 try:
  candidates=[path for path in manifest['inputs'] if Path(path).name==filename]
  if len(candidates)!=1:raise ValueError('expected exactly one frozen module input')
  frozen=Path(candidates[0])
  if hashlib.sha256(frozen.read_bytes()).hexdigest()!=manifest['inputs'][candidates[0]]:
   raise ValueError('frozen module input changed after staging')
  identity=run(['readelf','-n',str(frozen)])
  match=re.search(r'Build ID: ([0-9a-f]+)',identity.get('stdout',''))
  if identity.get('returncode')!=0 or not match:raise ValueError('module build ID unavailable')
  raw=(sysroot/'module'/name/'notes/.note.gnu.build-id').read_bytes()
  namesz,descsz,kind=struct.unpack_from('<III',raw)
  offset=12+((namesz+3)&~3)
  if kind!=3 or namesz!=4 or descsz==0 or offset+descsz>len(raw) or raw[12:16]!=b'GNU\0':
   raise ValueError('unexpected or truncated loaded build note')
  loaded=raw[offset:offset+descsz].hex()
  item.update({'expected_build_id':match[1],'loaded_build_id':loaded,'matches_frozen_bundle':loaded==match[1]})
 except (OSError,ValueError,struct.error) as error:item['error']=str(error)
 return item

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--stage-manifest',required=True,type=Path);a=p.parse_args()
 output=a.output.resolve()
 if Path('/boot') in output.parents or output==Path('/boot') or Path('/usr/lib/modules') in output.parents:raise ValueError('output outside boot/module paths required')
 a.output.mkdir(parents=True,exist_ok=False)
 manifest=json.loads(a.stage_manifest.read_text());cmdline=read('/proc/cmdline')
 params={name:read('/sys/module/thunderbolt/parameters/'+name) for name in ('allow_dp_tunnel','dprx_bypass','dprx_timeout')}
 checks={'kernelrelease_matches':os.uname().release==manifest['kernelrelease'],'bypass_on':params['dprx_bypass'].lower() in ('y','1'),'tunnel_allowed':params['allow_dp_tunnel'].lower() in ('y','1'),'timeout_15000':params['dprx_timeout']=='15000'}
 for token in ('thunderbolt.allow_dp_tunnel=1','thunderbolt.dprx_bypass=1','thunderbolt.dprx_timeout=15000'):
  checks['cmdline_'+token]=cmdline.split().count(token)==1
 modules={name:(Path('/sys/module')/name).is_dir() for name in ('phy_apple_atc','phy_apple_dpin','appledrm','thunderbolt','thunderbolt_apple')}
 loaded_identity={filename[:-3].replace('-','_'): module_identity(filename,manifest) for filename in ('phy-apple-atc.ko','phy-apple-dpin.ko','appledrm.ko','thunderbolt.ko','thunderbolt_apple.ko')}
 connectors=[]
 for path in sorted(Path('/sys/class/drm').glob('card*-*')):
  if not re.fullmatch(r'card\d+-(?:DP-\d+(?:-\d+)*|HDMI-[A-Za-z]+-\d+)',path.name):continue
  item={'name':path.name,'status':read(path/'status'),'enabled':read(path/'enabled'),'modes':read(path/'modes')}
  try:
   edid=(path/'edid').read_bytes();(a.output/(path.name+'-edid.bin')).write_bytes(edid)
   item.update({'edid_bytes':len(edid),'edid_sha256':hashlib.sha256(edid).hexdigest(),'edid_header_valid':edid[:8]==bytes.fromhex('00ffffffffffff00'),'edid_block_checksums_valid':bool(edid) and len(edid)%128==0 and all(sum(edid[i:i+128])%256==0 for i in range(0,len(edid),128))})
  except OSError as e:item['edid_error']=str(e)
  connectors.append(item)
 kernel=run(['journalctl','-k','-b','--no-pager','-o','short-monotonic']);(a.output/'kernel-journal.txt').write_text(kernel.get('stdout',''))
 result={'captured_epoch':time.time(),'source_revision':manifest['source_revision'],'stage_manifest_sha256':hashlib.sha256(a.stage_manifest.read_bytes()).hexdigest(),'uname':list(os.uname()),'cmdline':cmdline,'thunderbolt_parameters':params,'controlled_boot_checks':checks,'module_presence':modules,'loaded_module_identity':loaded_identity,'external_connectors':connectors,'lsmod':run(['lsmod']),'lsusb':run(['lsusb']),'kernel_journal_status':{key:value for key,value in kernel.items() if key!='stdout'},'qualification_note':'External DP/HDMI only; eDP excluded. No connector/picture success inferred from bypassed DPRX or USB enumeration. Collector does not reload drivers, change bypass, touch MMIO or move cables.'}
 (a.output/'controlled-test-results.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'output':str(a.output.resolve()),'controlled_boot_checks':checks,'all_five_modules_present':all(modules.values()),'external_connectors':connectors},indent=2))
if __name__=='__main__':main()
