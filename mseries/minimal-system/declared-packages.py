#!/usr/bin/env python3
# Lists packages named in mkosi configs and install scripts: declared-packages.py <all-package-names-file> <repo-root>
import re,glob,sys,os
names=set(open(sys.argv[1]).read().split())
root=sys.argv[2]
out={}
def add(p,src):
    out.setdefault(p,set()).add(src)
# mkosi conf files: Packages= blocks
for f in glob.glob(root+'/mkosi*/**/*.conf',recursive=True)+glob.glob(root+'/mkosi.conf'):
    if '/repos/' in f: continue
    inpk=False
    for l in open(f,errors='ignore'):
        s=l.rstrip('\n')
        if re.match(r'^(\w+Packages|Packages|BuildPackages)=',s):
            inpk=True; rest=s.split('=',1)[1].strip()
            for t in rest.split():
                if t in names: add(t,'mkosi:'+os.path.relpath(f,root))
            continue
        if inpk:
            if re.match(r'^\s+\S',s):
                t=s.strip().split()[0]
                if t in names: add(t,'mkosi:'+os.path.relpath(f,root))
            else: inpk=False
# scripts: tokens on apt install lines (and continued lines)
for f in glob.glob(root+'/**/*',recursive=True):
    if '/repos/' in f or '/.git/' in f or not os.path.isfile(f): continue
    if not re.search(r'\.(sh|chroot|py)$|/bin/',f) and not f.endswith('elementary-grow.sh'): continue
    try: txt=open(f,errors='ignore').read()
    except: continue
    for m in re.finditer(r'(?:apt-get|apt)\s+(?:-\S+\s+)*install\s+((?:[^\n]*\\\n)*[^\n]*)',txt):
        blob=m.group(1).replace('\\\n',' ')
        for t in re.split(r'[\s;|&<>()"\']+',blob):
            t=t.strip('$\\')
            if t in names: add(t,'script:'+os.path.relpath(f,root))
for p in sorted(out): print(p,'|'.join(sorted(out[p]))[:200])
