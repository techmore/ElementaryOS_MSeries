import os,sys,time
names=sys.argv[2:]; T=float(sys.argv[1]); hz=os.sysconf('SC_CLK_TCK')
def s():
    d={}
    for p in filter(str.isdigit,os.listdir('/proc')):
        try:
            c=open(f'/proc/{p}/comm').read().strip()
            f=open(f'/proc/{p}/stat').read().rsplit(')',1)[1].split()
            d[p]=(c,int(f[11])+int(f[12]))
        except: pass
    return d
a=s();time.sleep(T);b=s()
for p,(c,t) in b.items():
    if p in a and any(n in c for n in names): print("%-20s pid %-7s %.2f%% cpu (avg of %ds)"%(c,p,(t-a[p][1])/hz/T*100,T))
