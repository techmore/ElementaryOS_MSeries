"""Allowlisted public/synthetic qualification export; excludes app profiles, logs, audio."""
from pathlib import Path
import hashlib,json,re
repo=Path.cwd();work=repo.parent;out=repo/'mseries/local-ai/receipts/f5-english-2026-10-18';out.mkdir(parents=True,exist_ok=True)
def sanitize(v):
 if isinstance(v,dict):return {k:sanitize(x) for k,x in v.items()}
 if isinstance(v,list):return [sanitize(x) for x in v]
 if isinstance(v,str):
  v=v.replace(str(Path.home()),'<HOME>')
  return re.sub(r'/tmp/mseries-[^\s\"\']+', '<PRIVATE_TMP>',v)
 return v
def write(rel,value):
 p=out/rel;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(sanitize(value),indent=2,ensure_ascii=False)+'\n')
folders=sorted(p for p in work.glob('f5-*') if p.is_dir())
manifest={};snapshots={}
for folder in folders:
 files=[]
 for p in folder.rglob('*.json'):
  rel=p.relative_to(folder)
  if any(x in rel.parts for x in ['evaluated-source','source','private-audio','english-wav']):continue
  if not(p.name=='receipt.json' or p.name.endswith('-attempt.json') or p.name in ['attempt.json','classification.json','audio-verification.json','cpu-supervisor-receipt-failure.json','cpu.json','mlx.json','ane.json']):continue
  files.append(p)
 for p in files:
  value=json.loads(p.read_text());write(Path(folder.name)/p.relative_to(folder),value)
 if files:manifest[folder.name]=[p.relative_to(folder).as_posix() for p in files]
 source_files=[]
 for name in ['source','evaluated-source']:
  if(folder/name).is_dir():source_files+=list((folder/name).rglob('*.py'))
 for receipt in folder.rglob('receipt.json'):
  source=receipt.parent/'evaluated-source'
  if source.is_dir():source_files+=list(source.rglob('*.py'))
 mapping={}
 for p in sorted(set(source_files)):
  data=p.read_bytes();sha=hashlib.sha256(data).hexdigest();dest=out/'source-blobs'/(sha+'.py');dest.parent.mkdir(exist_ok=True);dest.write_bytes(data);mapping[p.relative_to(folder).as_posix()]=sha
 if mapping:snapshots[folder.name]=mapping
for name in ['nemotron-transcribe-source.json']:
 write(Path('pins')/name,json.loads((work/'speech-assets'/name).read_text()))
for name,path in [('nemotron-mlx.json',work/'speech-assets/nemotron-mlx/source-pin.json'),('mlx-audio-0.5.9.json',work/'mlx-audio-nemotron-probe/source-pin.json'),('parakeet-mlx.json',work/'speech-assets/mlx-parakeet/source-pin.json')]:
 write(Path('pins')/name,json.loads(path.read_text()))
write(Path('cohorts.json'),manifest);write(Path('snapshots.json'),snapshots)
# Metric interpretation never replaces retained original receipts.
corrected=[]
for p in (work/'f5-app-qualified-v1').glob('*/receipt.json'):
 d=json.loads(p.read_text());stage=d.get('speech',{});values=[v for v in [stage.get('first_widget_text_s'),stage.get('first_provisional_s')] if v is not None]
 expected=re.findall(r'\w+',stage.get('reference','').lower());actual=re.findall(r'\w+',stage.get('final_text','').lower())
 corrected.append({'case':d['framework'],'original_receipt_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'original_assertion_passed':d.get('passed'),'failure_retained':d.get('failure_detail'),'corrected_criterion':'Exact final normalized words and any real visible text before nominal audio end; speculative preedit is not required','exact_final_words':bool(expected) and actual==expected,'first_visible_s':min(values) if values else None,'visible_during_speech':bool(values) and min(values)<stage['audio_duration_s'],'scope':'Read-only interpretation of original recorded traces; no model rerun. Current production suppresses speculative preedit.'})
write(Path('early-stable-words-interpretation.json'),corrected)
(out/'export-evidence.py').write_bytes(Path('../export-f5-evidence.py').read_bytes())
(out/'README.md').write_text('''# English F5 evidence — M1 Pro32GB, October18\n\n[Acceptance report](../../../dictation/F5-ENGLISH-ACCEPTANCE.md) and\n[canonical index](../../../dictation/QUALIFICATION-INDEX.md) define scopes and\ncontinuation. Cohorts preserve original successes, failures and unscored attempts.\nSource snapshots are content-addressed exact public Python bytes, deduplicated in\nsource-blobs/. snapshots.json reconstructs each cohort-relative layout. Model and\nruntime pins appear in receipts/pins; weights are not redistributed.\n\nFour-toolkit original preedit-only assertions remain failed; a separately labeled\nread-only interpretation uses existing early stable words, without model reruns.\nBrowser rich-compose v3/v4 are real product failures, not harness-only failures;\ncurrent speculative-input suppression passes v5. Source/criteria changed openly.\nCPU sustained telemetry save failure remains; completed CPU trials were not rerun.\n\nSource audio is public LibriSpeech CC-BY4.0, Panayotov/Chen/Povey/Khudanpur,\nhttps://www.openslr.org/12 . IDs, hashes and reference words are in receipts.\nNo model weights, audio/WAV, private app settings, Newelle logs, tasks, journals,\ncredentials or owner content are exported. Voice output text is synthetic/public.\nHome/temp paths are role placeholders. Never copy whole private queue directories\nto publish; export-evidence.py shows the allowlist.\n''')
checks=out/'checksums.json'
if checks.exists():checks.unlink()
write(Path('checksums.json'),{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()})
for p in out.rglob('*'):
 if p.is_file():
  text=p.read_text();assert str(Path.home()) not in text,p;assert not re.search(r'https?://[^\s]+[?&]Signature=',text),p
print('Exported',len(manifest),'cohorts,',len(list((out/'source-blobs').glob('*.py'))),'source blobs')
