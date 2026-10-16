"""Mirror a picture along joined upright boards without moving their footprint."""
import math
from npexact import ddot


def mirror_screen(faces,sky,tiles,log):
    """Ordinary face records in/out; preserve untouched records and no-op list identity."""
    def length(a,b):
        d=tuple(a[k]-b[k] for k in range(len(a)))
        return math.sqrt(ddot(d,d))
    B=[]
    for w,L in enumerate((faces,sky)):
        for i,fc in enumerate(L):
            if str(fc[0]).split('|')[0] not in tiles or len(fc[2])!=4:continue
            P=[tuple(map(float,p)) for p in fc[2]];U=[tuple(map(float,u)) for u in fc[3]]
            if len(U)!=4 or any(len(p)!=3 for p in P) or any(len(u)!=2 for u in U):
                raise ValueError('buildmirror: four 3D corners and UV pairs required')
            if any(not math.isfinite(v) for rows in (P,U) for p in rows for v in p):
                raise ValueError('buildmirror: finite positions and UVs required')
            # Four-element NumPy quicksort is insertion-sorted: ties keep order.
            o=sorted(range(4),key=lambda j:P[j][1]);b0,b1=o[:2]
            t0=min(o[2:],key=lambda j:length((P[j][0],P[j][2]),(P[b0][0],P[b0][2])))
            t1=next(j for j in o[2:] if j!=t0)
            B.append(dict(w=w,i=i,fc=fc,P=P,U=U,b=[b0,b1],t=[t0,t1]))
    if len(B)<2:return faces,sky
    def xz(bd,e):
        p=bd['P'][bd['b'][e]];return p[0],p[2]
    def near(p,q):return length(p,q)<.5
    ends=[(k,e) for k,bd in enumerate(B) for e in (0,1)
          if not any(near(xz(bd,e),xz(other,e2)) for k2,other in enumerate(B) if k2!=k for e2 in (0,1))]
    if not ends:
        log('       mirror_groups: the boards make a ring, not mirrored');return faces,sky
    k,e=ends[0];chain=[(k,e)];left=set(range(len(B)))-{k}
    while left:
        tip=xz(B[chain[-1][0]],1-chain[-1][1])
        nx=[(k2,e2) for k2 in left for e2 in (0,1) if near(tip,xz(B[k2],e2))]
        if not nx:
            log('       mirror_groups: %d of %d boards do not join the others, not mirrored'%(len(left),len(B)))
            return faces,sky
        chain.append(nx[0]);left.discard(nx[0][0])
    seg=[];t=0.
    for k,e in chain:
        bd=B[k];ln=length(xz(bd,1-e),xz(bd,e))
        seg.append(dict(bd=bd,s=t,e=t+ln,bs=bd['b'][e],be=bd['b'][1-e],ts=bd['t'][e],te=bd['t'][1-e]));t+=ln
    Lt=t;new={0:[],1:[]}
    def lerp(a,b,f):return tuple(a[k]+f*(b[k]-a[k]) for k in range(len(a)))
    for pk in seg:
        for gj in seg:
            ta,tb=max(Lt-pk['e'],gj['s']),min(Lt-pk['s'],gj['e'])
            if tb-ta<1e-4:continue
            Pj,Uk=gj['bd']['P'],pk['bd']['U']
            def g(q):return (q-gj['s'])/(gj['e']-gj['s'])
            def f(q):return (Lt-q-pk['s'])/(pk['e']-pk['s'])
            pt={}
            for dst,a,b,ua,ub,where in ((gj['bs'],gj['bs'],gj['be'],pk['bs'],pk['be'],ta),
                                        (gj['be'],gj['bs'],gj['be'],pk['bs'],pk['be'],tb),
                                        (gj['ts'],gj['ts'],gj['te'],pk['ts'],pk['te'],ta),
                                        (gj['te'],gj['ts'],gj['te'],pk['ts'],pk['te'],tb)):
                pt[dst]=lerp(Pj[a],Pj[b],g(where)),lerp(Uk[ua],Uk[ub],f(where))
            new[gj['bd']['w']].append((pk['bd']['fc'][0],gj['bd']['fc'][1],[pt[q][0] for q in range(4)],[pt[q][1] for q in range(4)]))
    gone={(bd['w'],bd['i']) for bd in B}
    faces=[fc for i,fc in enumerate(faces) if (0,i) not in gone]+new[0]
    sky=[fc for i,fc in enumerate(sky) if (1,i) not in gone]+new[1]
    log('       boards mirrored as one picture, in place (mirror_groups): %d boards, screen %.1f m, now %d polygons'%(len(B),Lt,len(new[0])+len(new[1])))
    return faces,sky
