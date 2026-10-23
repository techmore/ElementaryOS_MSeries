"""Offline tests for download integrity and admission; no models or engines run."""
import unittest, tempfile, json, hashlib, io, runpy, sys, contextlib
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
SRC=Path(__file__).resolve().parents[1]/'src'
class Adapters(unittest.TestCase):
 def download(self,root,content,sha):
  info={'sha':'revision','siblings':[{'rfilename':'model.gguf','lfs':{'size':len(content),'sha256':sha}}]}
  responses=iter([io.BytesIO(json.dumps(info).encode()),io.BytesIO(content)])
  with patch('shutil.disk_usage',return_value=SimpleNamespace(free=20*1024**3)),patch.object(sys,'argv',['download','repo','model.gguf',str(root)]),patch('urllib.request.urlopen',side_effect=lambda *a,**k:next(responses)),contextlib.redirect_stdout(io.StringIO()):
   runpy.run_path(str(SRC/'download_model.py'),run_name='__main__')
 def test_verified_download_records_revision_and_hash(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);content=b'test model';sha=hashlib.sha256(content).hexdigest();self.download(root,content,sha)
   self.assertEqual((root/'model.gguf').read_bytes(),content)
   self.assertEqual(json.loads((root/'model.gguf.json').read_text())['sha256'],sha)
 def test_corrupt_download_is_not_installed(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp)
   with self.assertRaises(SystemExit):self.download(root,b'bad','0'*64)
   self.assertFalse((root/'model.gguf').exists());self.assertFalse((root/'model.gguf.part').exists())
 def test_local_admission_refuses_low_memory_without_starting_worker(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'models').mkdir();model=root/'models/stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf';model.write_bytes(b'fixture')
   recipe=dict(model_id=str(model),lora_id='',width=512,height=512,batch_size=1,prompt='test')
   original=Path.read_text
   def read(path,*a,**k):return 'MemAvailable: 1000 kB\n' if str(path)=='/proc/meminfo' else original(path,*a,**k)
   with patch.object(sys,'argv',['local',str(root),json.dumps(recipe)]),patch.object(Path,'read_text',read),patch('subprocess.Popen') as launch,contextlib.redirect_stderr(io.StringIO()):
    with self.assertRaises(SystemExit):runpy.run_path(str(SRC/'local_generation.py'),run_name='__main__')
    launch.assert_not_called()
   self.assertFalse((root/'generation.lock').exists())
   self.assertIn('9 GiB',json.loads((root/'current-job.json').read_text())['status'])
 def test_real_subprocess_preview_transport_and_final_metadata(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'models').mkdir();(root/'engine').mkdir()
   model=root/'models/stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf';model.write_bytes(b'fixture weights')
   png=(SRC.parent/'tests/fixtures/tiny.png').read_bytes()
   engine=root/'engine/sd-cli'
   engine.write_text("#!/usr/bin/env python3\nimport sys,time\nfrom pathlib import Path\na=sys.argv\np=a[a.index('--preview-path')+1]\nfor i in range(2):\n Path(p.replace('%03d',str(i).zfill(3))).write_bytes(bytes.fromhex("+repr(png.hex())+"))\n time.sleep(.45)\nPath(a[a.index('-o')+1]).write_bytes(bytes.fromhex("+repr(png.hex())+"))\n")
   engine.chmod(0o755)
   recipe=dict(model_id=str(model),lora_id='',width=512,height=512,batch_size=1,prompt='transport fixture, not an AI run',negative_prompt='',seed=-1,steps=2,cfg_scale=7,sampler='euler')
   original=Path.read_text
   def read(path,*a,**k):return 'MemAvailable: 12000000 kB\n' if str(path)=='/proc/meminfo' else original(path,*a,**k)
   with patch.object(sys,'argv',['local',str(root),json.dumps(recipe)]),patch.object(Path,'read_text',read):
    runpy.run_path(str(SRC/'local_generation.py'),run_name='__main__')
   job=json.loads((root/'current-job.json').read_text());saved=json.loads(Path(job['recipe_path']).read_text())
   self.assertFalse(job['running']);self.assertEqual(saved['preview_count'],2);self.assertGreaterEqual(saved['seed'],0)
   self.assertIsNotNone(saved['time_to_first_preview_seconds']);self.assertTrue(Path(saved['image_path']).is_file())
   self.assertIn('--preview',saved['engine_arguments']);self.assertFalse((root/'generation.lock').exists())
 def test_sweep_retains_fixed_seed_and_separate_results(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);(root/'models').mkdir();(root/'images').mkdir()
   for name in ['stable-diffusion-v1-5-pruned-emaonly-Q4_0.gguf','stable-diffusion-v1-5-pruned-emaonly-Q8_0.gguf']:(root/'models'/name).write_bytes(b'fixture')
   code="import sys,json,time;from pathlib import Path;b=Path(sys.argv[1]);r=json.loads(sys.argv[2]);p=b/'images'/('fixture-'+str(time.time_ns())+'.json');r['image_path']=str(p.with_suffix('.png'));p.write_text(json.dumps(r));(b/'current-job.json').write_text(json.dumps({'recipe_path':str(p)}))"
   recipe=dict(seed=424242,prompt='fixture')
   with patch.object(sys,'argv',['sweep',str(root),json.dumps(recipe),json.dumps({'kind':'models','review':False}),code,'']):
    runpy.run_path(str(SRC/'sweep_runner.py'),run_name='__main__')
   manifest=json.loads(Path((root/'latest-sweep.txt').read_text()).read_text())
   self.assertEqual(manifest['status'],'Complete');self.assertEqual(len(manifest['runs']),2)
   self.assertEqual([run['settings']['seed'] for run in manifest['runs']],[424242,424242])
   self.assertNotEqual(manifest['runs'][0]['recipe_path'],manifest['runs'][1]['recipe_path'])
   self.assertFalse((root/'batch.lock').exists())
if __name__=='__main__':unittest.main()
