import re,sys
p=sys.argv[1]
lines=open(p,'r',errors='replace').read().splitlines()
W=[l for l in lines if '[spu2:wall]' in l]
if not W: print("  no wall lines"); sys.exit()
def parse(l):
    d=dict(re.findall(r'(\w+)=(\d+)',l)); return int(d['pushed']),int(d['played']),int(d['dropped']),int(d['secs'])
f=parse(W[0]); l=parse(W[-1]); ds=l[3]-f[3] or 1
dp=l[0]-f[0]; dl=l[1]-f[1]; dd=l[2]-f[2]
print("  window %ds: produced %.1f blk/s (%.2fx rt) | consumed %.1f blk/s (%.2fx rt) | dropped %.1f/s (%.0f%% of attempts)"%(
 ds,dp/ds,dp/ds*256/48000,dl/ds,dl/ds*256/48000,dd/ds,100.0*dd/(dp+dd) if dp+dd else 0))
for tag in ('[spu2:queue]','[spu2:arm]'):
    v=[x for x in lines if tag in x]
    print("  %-13s %s"%(tag,v[-1].strip() if v else "none"))
