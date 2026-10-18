import time,statistics as st
H='/sys/class/hwmon/hwmon2/power1_input'
def cpu():
    v=list(map(int,open('/proc/stat').readline().split()[1:9])); return sum(v), v[3]+v[4]
xs=[];ys=[]
t0,i0=cpu()
for k in range(240):
    time.sleep(1); t1,i1=cpu(); w=int(open(H).read())/1e6
    xs.append(100*(1-(i1-i0)/(t1-t0))); t0,i0=t1,i1; ys.append(w)
n=len(xs); mx=sum(xs)/n; my=sum(ys)/n
sxx=sum((x-mx)**2 for x in xs); sxy=sum((x-mx)*(y-my) for x,y in zip(xs,ys)); syy=sum((y-my)**2 for y in ys)
b=sxy/sxx; a=my-b*mx; q=sorted(ys)
print(f"n={n} median={st.median(ys):.2f}W mean={my:.2f}W p10={q[n//10]:.2f} p90={q[9*n//10]:.2f}")
print(f"cpu busy mean={mx:.1f}%  fit W={a:.2f}+{b:.3f}*busy% r2={sxy*sxy/sxx/syy:.2f}")
