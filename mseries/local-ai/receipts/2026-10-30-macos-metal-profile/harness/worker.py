import sys,os,json,time,hashlib,importlib.util
from pathlib import Path
model_dir,which,prompt,max_tokens,out,lfm_file=sys.argv[1:]
if lfm_file!='-':
 p=Path(lfm_file);expected='a4096cddc8f0d3f7923008b2e6afb896dabc9aef963a5ebe7d76d13a6069b0c4'
 if hashlib.sha256(p.read_bytes()).hexdigest()!=expected: raise RuntimeError('LFM3 implementation checksum mismatch')
 spec=importlib.util.spec_from_file_location('mlx_lm.models.lfm3',str(p));mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
from mlx_lm import load,stream_generate
from mlx_lm.sample_utils import make_sampler
import mlx.core as mx
wall_start=time.strftime('%Y-%m-%d %H:%M:%S %Z%z'); started=time.monotonic(); model,tok=load(model_dir)
prompt=tok.apply_chat_template([{'role':'user','content':prompt}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
ids=tok.encode(prompt); sampler=make_sampler(temp=0)
for _ in stream_generate(model,tok,prompt,max_tokens=int(max_tokens),sampler=sampler):pass
mx.synchronize(); ready=time.monotonic()-started;start=time.monotonic();first=None;tokens=[];text=''
for r in stream_generate(model,tok,prompt,max_tokens=int(max_tokens),sampler=sampler):
 if first is None:first=time.monotonic()-start
 tokens.append(r.token);text+=r.text
mx.synchronize();total=time.monotonic()-start
res={'model':which,'prompt_tokens':len(ids),'prompt_token_sha256':hashlib.sha256(json.dumps(ids).encode()).hexdigest(),'ready_s':ready,'ttft_s':first,'total_s':total,'completion_tokens':len(tokens),'decode_estimate_tps':(len(tokens)-1)/(total-first) if first is not None and len(tokens)>1 and total>first else None,'token_ids':tokens,'text':text,'start_time':wall_start,'end_time':time.strftime('%Y-%m-%d %H:%M:%S %Z%z'),'peak_memory_bytes':mx.get_peak_memory()}
Path(out).write_text(json.dumps(res,indent=2)+'\n');print(json.dumps({k:v for k,v in res.items() if k not in ('text','token_ids')}),flush=True)
