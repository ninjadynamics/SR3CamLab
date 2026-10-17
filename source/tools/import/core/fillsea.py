"""Additive NumPy-free sea clipping; the legacy caller remains unchanged."""
import math
import geobuf


def _bound(v, upper, ceil):
    v=math.ceil(v) if ceil else math.floor(v)
    # Match NumPy's Windows int32 cast before clipping, including overflow.
    if not -(1<<31)<=v<(1<<31):v=-(1<<31)
    return max(0,min(v,upper))


def sea_clip(sea,land,level,cell,sub=10.,step=2.5,max_h=25.):
    """Return (faces, integer area removed), retaining untouched face storage.

    Inputs use the importer's ordinary float64-compatible face records. The
    lattice and neighbour erosion follow fill1995.sea_clip in the same order.
    Finite dimensions and a bounded lattice are required before allocation.
    """
    if not sea:return sea,0
    for name,v in (('cell',cell),('sub',sub),('step',step)):
        if not math.isfinite(v) or v<=0:raise ValueError('fillsea: invalid '+name)
    if not math.isfinite(level) or not math.isfinite(max_h):raise ValueError('fillsea: nonfinite height')
    points=[q for f in sea for q in f[2]]
    if not points or any(len(q)!=3 or not all(math.isfinite(v) for v in q) for q in points):
        raise ValueError('fillsea: invalid sea coordinates')
    x0=min(float(q[0]) for q in points);z0=min(float(q[2]) for q in points)
    nx=int(round((max(float(q[0]) for q in points)-x0)/step))+1
    nz=int(round((max(float(q[2]) for q in points)-z0)/step))+1
    k=int(round(sub/step));m=int(round(cell/sub))
    if k<1 or m<1:raise ValueError('fillsea: subdivision smaller than lattice')
    if nx*nz>40000000:raise ValueError('fillsea: lattice too large')
    R=bytearray(nx*nz)
    g=geobuf.prep(land);nr=g.nr.view();lo=g.lo.view();hi=g.hi.view()
    xyz=g.X.view();off=g.off.view()
    if any(not math.isfinite(v) for v in xyz):raise ValueError('fillsea: nonfinite land coordinates')
    for fi,(mat,sec,Q,UV) in enumerate(land):
        if str(mat).endswith('_t') or abs(nr[3*fi+1])<.3 or hi[3*fi+1]<=level or lo[3*fi+1]>level+max_h:continue
        a=_bound((lo[3*fi]-x0)/step,nx-1,True);b=_bound((hi[3*fi]-x0)/step,nx-1,False)
        c=_bound((lo[3*fi+2]-z0)/step,nz-1,True);d=_bound((hi[3*fi+2]-z0)/step,nz-1,False)
        if b<a or d<c:continue
        H=[(xyz[3*i],xyz[3*i+2]) for i in range(off[fi],off[fi+1])]
        ar=sum(H[i][0]*H[(i+1)%len(H)][1]-H[(i+1)%len(H)][0]*H[i][1] for i in range(len(H)))
        edges=[(p,q[0]-p[0],q[1]-p[1]) for p,q in zip(H,H[1:]+H[:1])]
        for i in range(a,b+1):
            x=x0+i*step
            for j in range(c,d+1):
                if R[i*nz+j]:continue
                z=z0+j*step;inside=True
                for p,dx,dz in edges:
                    cr=dx*(z-p[1])-dz*(x-p[0])
                    if (cr< -1e-6 if ar>0 else cr>1e-6):inside=False;break
                if inside:R[i*nz+j]=1
    mx=(nx-1)//k;mz=(nz-1)//k;C=bytearray(mx*mz)
    for i in range(mx):
        for j in range(mz):
            C[i*mz+j]=all(all(R[t*nz+j*k:t*nz+(j+1)*k+1]) for t in range(i*k,(i+1)*k+1))
    drop=bytearray(mx*mz)
    for i in range(1,mx-1):
        for j in range(1,mz-1):
            drop[i*mz+j]=all(all(C[t*mz+j-1:t*mz+j+2]) for t in (i-1,i,i+1))
    out=[]
    for mat,sec,Q,UV in sea:
        i0=int(round((Q[0][0]-x0)/sub));j0=int(round((Q[0][2]-z0)/sub))
        # Preserve NumPy's clipped/negative slice semantics for edge quads.
        rows=range(*slice(i0,i0+m).indices(mx));cols=range(*slice(j0,j0+m).indices(mz))
        if not any(drop[i*mz+j] for i in rows for j in cols):out.append((mat,sec,Q,UV));continue
        if len(rows)<m or len(cols)<m:raise IndexError('fillsea: partial sea block with clipped cells')
        for a in range(m):
            for b in range(m):
                if drop[rows[a]*mz+cols[b]]:continue
                xa,xb=Q[0][0]+a*sub,Q[0][0]+(a+1)*sub;za,zb=Q[0][2]+b*sub,Q[0][2]+(b+1)*sub
                out.append((mat,sec,[(xa,level,za),(xb,level,za),(xb,level,zb),(xa,level,zb)],[(a/m,b/m),((a+1)/m,b/m),((a+1)/m,(b+1)/m),(a/m,(b+1)/m)]))
    return out,int(sum(drop)*sub*sub)
