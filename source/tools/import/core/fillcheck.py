"""NumPy-free coplanar-overlap diagnostics; no legacy INFO mutation."""
import collections
import math
import geobuf
from npexact import ddot


def overlap2d(A,B,shrink=.02):
    """Legacy separating-axis test for convex two-dimensional polygons."""
    for P,Q in ((A,B),(B,A)):
        for i in range(len(P)):
            a,b=P[i],P[(i+1)%len(P)];e=(b[0]-a[0],b[1]-a[1]);ln=math.sqrt(ddot(e,e))
            if ln<1e-9:continue
            ax=(-e[1]/ln,e[0]/ln);p=[ddot(v,ax) for v in P];q=[ddot(v,ax) for v in Q]
            if max(p)-min(q)<shrink or max(q)-min(p)<shrink:return False
    return True


def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def coplanar_report(old,new,tol=.02):
    """Return (overlapping_pair_count, first_six_material_pairs).

    The grid traversal and pair-set order match the legacy diagnostic. All
    geometry is read only. Invalid coordinates and oversized grids fail before
    constructing an unbounded bucket table.
    """
    allf=list(old)+list(new);g=geobuf.prep(allf);nr=g.nr.view();lo=g.lo.view();hi=g.hi.view();X=g.X.view();off=g.off.view()
    if any(not math.isfinite(v) for v in X):raise ValueError('fillcheck: nonfinite geometry')
    if any(n<1 for n in g.lens.view()):raise ValueError('fillcheck: empty polygon')
    recs=[];bounds=[];members=0
    for i in range(len(allf)):
        l=tuple(lo[3*i:3*i+3]);h=tuple(hi[3*i:3*i+3]);box=(int(l[0]//16),int(h[0]//16),int(l[2]//16),int(h[2]//16))
        members+=(box[1]-box[0]+1)*(box[3]-box[2]+1)
        if members>40000000:raise ValueError('fillcheck: grid too large')
        bounds.append(box);recs.append((tuple(nr[3*i:3*i+3]),l,h,[tuple(X[3*q:3*q+3]) for q in range(off[i],off[i+1])]))
    grid=collections.defaultdict(list)
    for i,(x0,x1,z0,z1) in enumerate(bounds):
        for a in range(x0,x1+1):
            for b in range(z0,z1+1):grid[a,b].append(i)
    bad=set()
    for i in range(len(old),len(allf)):
        normal,l,h,P=recs[i]
        if not any(normal):continue
        ref=(1.,0.,0.) if abs(normal[0])<.9 else (0.,1.,0.);e1=_cross(normal,ref);ln=math.sqrt(ddot(e1,e1));e1=tuple(v/ln for v in e1);e2=_cross(normal,e1)
        x0,x1,z0,z1=bounds[i]
        for a in range(x0,x1+1):
            for b in range(z0,z1+1):
                for j in grid[a,b]:
                    pair=(min(i,j),max(i,j))
                    if j==i or pair in bad:continue
                    n2,l2,h2,P2=recs[j]
                    if abs(ddot(normal,n2))<.9995 or any(l[k]>h2[k] or l2[k]>h[k] for k in range(3)):continue
                    if max(abs(ddot([q[k]-P[0][k] for k in range(3)],normal)) for q in P2)>tol:continue
                    A=[(ddot(q,e1),ddot(q,e2)) for q in P];B=[(ddot(q,e1),ddot(q,e2)) for q in P2]
                    if overlap2d(A,B):bad.add(pair)
    return len(bad),[(allf[i][0],allf[j][0]) for i,j in list(bad)[:6]]
