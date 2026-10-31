import os,sys,time,subprocess,json,shutil,re
name=sys.argv[1];folder=os.path.abspath('work/mac-scoreboard/'+name);target='outputs/mac-scoreboard';lfm=os.path.abspath('work/mac-scoreboard/lfm3.py') if name=='lfm3' else '-'
prompts=[('short','Explain in plain language how a rainbow forms. Give four distinct sentences.',32),('long','Explain in detail how a rainbow forms, including refraction, reflection, color and viewing angle. Write at least 350 words.',256)]
for label,prompt,n in prompts:
 for i in range(1,4):
  free=shutil.disk_usage('.').free
  memory=subprocess.run(['memory_pressure'],capture_output=True,text=True).stdout
  match=re.search(r'System-wide memory free percentage: (\d+)%',memory)
  avail=int(match.group(1)) if match else None
  print(f'{name} {label} {i}: disk {free/2**30:.1f} GiB memory free {avail}%',flush=True)
  if free<6*2**30 or avail is None or avail < 25:
   print('Stopped before admission: disk or memory headroom below guard',flush=True);sys.exit(3)
  out=f'{target}/{name}-{label}-{i}.json'
  env=dict(os.environ,HF_HUB_OFFLINE='1',OMP_NUM_THREADS='2',OPENBLAS_NUM_THREADS='2')
  run=subprocess.run(['nice','-n','10',sys.executable,'work/mac-scoreboard/worker.py',folder,name,prompt,str(n),out,lfm],env=env,timeout=300)
  if run.returncode:print('failed',run.returncode,flush=True);sys.exit(run.returncode)
  time.sleep(15)
