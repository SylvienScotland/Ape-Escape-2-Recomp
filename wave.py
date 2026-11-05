import struct,sys,math,statistics
f=sys.argv[1]
d=open(f,'rb').read(); s=struct.unpack('<%dh'%(len(d)//2),d[:len(d)//2*2])
L=s[0::2]; R=s[1::2]; n=len(L)
print("  %s: %d frames = %.1f s"%(f,n,n/48000))
def metrics(x):
    m=len(x); rms=math.sqrt(sum(v*v for v in x)/m); pk=max(abs(v) for v in x)
    zc=sum(1 for i in range(1,m) if (x[i-1]<0)!=(x[i]<0))
    dd=sum(abs(x[i]-x[i-1]) for i in range(1,m))/(m-1)
    return rms,pk,pk/rms if rms else 0,dd/rms if rms else 0,100.0*zc/m
rms,pk,cr,dr,zc=metrics(L)
print("  whole-file L: rms=%.0f pk=%d crest=%.2f |d|/rms=%.3f zcr=%.1f%%"%(rms,pk,cr,dr,zc))
B=256
bl=[metrics(L[i:i+B]) for i in range(0,n-B,B)]
print("  per-256-frame block medians: rms=%.0f crest=%.2f |d|/rms=%.3f zcr=%.1f%%"%(
  statistics.median(b[0] for b in bl),statistics.median(b[2] for b in bl),
  statistics.median(b[3] for b in bl),statistics.median(b[4] for b in bl)))
def seam(idx):
    if idx<65 or idx>=n-65: return None
    j=abs(L[idx]-L[idx-1]); loc=statistics.median(abs(L[i]-L[i-1]) for i in range(idx-64,idx+64) if i!=idx)
    return j/loc if loc else None
b=[seam(i) for i in range(B,n,B)]; b=[x for x in b if x]
if b: print("  seam at 256-frame boundaries: median=%.2f >4x=%.1f%%"%(statistics.median(b),100.0*sum(1 for x in b if x>4)/len(b)))
