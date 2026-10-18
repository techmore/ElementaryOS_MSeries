"""Export only allowlisted public-file evidence; never copy logs, audio or settings."""
import hashlib,json,pathlib,shutil
repo=pathlib.Path.cwd();work=repo.parent
out=repo/'mseries/local-ai/receipts/realtime-english-2026-10-18'
out.mkdir(parents=True,exist_ok=False)
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
 if isinstance(v,list):return [clean(x) for x in v]
 if isinstance(v,str):return v.replace(str(pathlib.Path.home()),'<HOME>')
 return v
def emit(path,value):
 p=out/path;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(clean(value),indent=2,ensure_ascii=False)+'\n')
cohorts=['realtime-speech-v1','realtime-nemotron-v2','english-realtime-v1','mlx-realtime-v1']
snapshots={}
for cohort in cohorts:
 folder=work/cohort
 for p in sorted(folder.glob('*.json')):emit(pathlib.Path(cohort)/p.name,json.loads(p.read_text()))
 if (folder/'english-panel/receipt.json').exists():emit(pathlib.Path(cohort)/'english-panel/receipt.json',json.loads((folder/'english-panel/receipt.json').read_text()))
 source=folder/'evaluated-source'
 sources=list(source.rglob('*.py')) if source.exists() else [folder/'realtime-bench.py']
 if (folder/'english-panel/evaluated-source').exists():sources+=list((folder/'english-panel/evaluated-source').rglob('*.py'))
 mapping={}
 for p in sources:
  data=p.read_bytes();sha=hashlib.sha256(data).hexdigest()
  dest=out/'source-blobs'/(sha+'.py');dest.parent.mkdir(exist_ok=True);dest.write_bytes(data)
  mapping[str(p.relative_to(folder))]=sha
 snapshots[cohort]=mapping
# The rejected original GGUF is a runtime-format failure; no completed quality cases.
for name in ['nemotron-cpu.json','nemotron-cpu-attempt.json']:
 emit(pathlib.Path('unsupported-original-gguf')/name,json.loads((work/'realtime-live-v1'/name).read_text()))
for name in ['nemotron-source.json','nemotron-transcribe-source.json']:
 emit(pathlib.Path('pins')/name,json.loads((work/'speech-assets'/name).read_text()))
emit(pathlib.Path('pins/mlx-parakeet.json'),json.loads((work/'speech-assets/mlx-parakeet/source-pin.json').read_text()))
# Do not export expiring signed download URLs.
clips=[]
for row in json.loads((work/'speech-assets/public-clips/expanded-manifest.json').read_text()):
 row={k:v for k,v in row.items() if k!='src'};p=work/'speech-assets/public-clips'/(row['id']+'-16k.wav')
 row['derived_16k_mono_s16_sha256']=hashlib.sha256(p.read_bytes()).hexdigest();clips.append(row)
emit(pathlib.Path('pins/additional-public-clips.json'),clips)
audit=work/'speech-research-2026-10-18';repos=[]
for name in ['joshuaswarren__omarchy-mlx','joshuaswarren__omarchy-ane','omacom__omarchy-mac','omacom__omarchy-mac-pkgs']:
 d=json.loads((audit/(name+'.json')).read_text());repos.append({'repo':d['repo'],'default_branch':d['default_branch'],'branches_enumerated':len(d['branches']),'default_sha':next(x['sha'] for x in d['branches'] if x['name']==d['default_branch']),'release':d.get('release')})
branches=json.loads((audit/'joshuaswarren__omarchy-mlx.json').read_text())['branches'];comparisons=[]
for p in audit.glob('compare-*.json'):
 d=json.loads(p.read_text());url=d['html_url'];ref=url.split('...')[-1];branch=next((x for x in branches if x['sha']==ref),None)
 comparisons.append({'comparison_url':url,'base_sha':d['base_commit']['sha'],'head':branch,'ahead_by':d['ahead_by'],'behind_by':d['behind_by'],'changed_paths':[x['filename'] for x in d['files']]})
emit(pathlib.Path('source-audit.json'),{'date':'2026-10-18','scope':'Point-in-time public branch/source audit, not speed measurements on other hardware','repositories':repos,'mlx_comparisons':comparisons,'omarchy_mx':json.loads((audit/'omarchy-mx-audit.json').read_text())})
emit(pathlib.Path('snapshots.json'),snapshots)
# New English panel regression does not rerun inference or replace the earlier model cohort.
shutil.copyfile(work/'export-realtime-receipts.py',out/'export-receipts.py')
emit(pathlib.Path('checksums.json'),{p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()})
print('Exported',len(list(out.rglob('*.json'))),'JSON files and',len(list((out/'source-blobs').glob('*.py'))),'deduplicated source blobs')
