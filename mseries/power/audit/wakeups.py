import os,time,sys
def snap():
    d={}
    for p in os.listdir('/proc'):
        if not p.isdigit(): continue
        try:
            c=open(f'/proc/{p}/comm').read().strip()
            sw=0
            for l in open(f'/proc/{p}/status'):
                if 'ctxt_switches' in l: sw+=int(l.split()[1])
            st=open(f'/proc/{p}/stat').read().rsplit(')',1)[1].split()
            d[int(p)]=(c,sw,int(st[11])+int(st[12]))
        except Exception: pass
    return d
T=float(sys.argv[1]); a=snap(); time.sleep(T); b=snap()
r=[]
for p,(c,s,t) in b.items():
    if p in a and a[p][0]==c: r.append(((s-a[p][1])/T,(t-a[p][2])/T/os.sysconf('SC_CLK_TCK')*100,c,p))
print("top ctx-switches/s (voluntary+invol) and cpu%")
for x in sorted(r,reverse=True)[:22]: print("%8.1f sw/s %6.1f%% %s(%d)"%x)
print("--- by cpu");
for x in sorted(r,key=lambda x:-x[1])[:12]: print("%8.1f sw/s %6.1f%% %s(%d)"%x)
print("total sw/s %.0f"%sum(x[0] for x in r))
