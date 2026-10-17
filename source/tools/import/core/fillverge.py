"""NumPy-free forest verge retile selection with explicit class/origin maps."""
import fillroad
import geobuf
from npexact import pwsum


def _center(P):
    # The original [:,[0,2]] produces contiguous columns before mean(0).
    return tuple(pwsum([float(q[a]) for q in P])/len(P) for a in (0,2))


def _nearest(points,c):
    def distance(p):
        x=p[0]-c[0];z=p[1]-c[1];return x*x+z*z
    k=min(range(len(points)),key=lambda k:distance(points[k]))
    return k,distance(points[k])


def retile_verge(verge,faces,rd,labels,origin=None,log=print,reach=60.):
    """Return retiled face records; leave corners, UVs and inputs unchanged.

    labels maps tile names to class names. origin maps composed tile names to
    their source tiles. Road coordinates use fillroad's checked f4/f8 Arr API.
    """
    origin={} if origin is None else origin
    cls=lambda m:labels.get(origin.get(m,m))
    hw,V,n,b=fillroad._inputs(rd);v=V.view()
    cen=[(v[3*(i*b+hw)],v[3*(i*b+hw)+2]) for i in range(n)]
    ks=[_nearest(cen,_center(P))[0] for mat,sec,P,UV in faces if str(mat).endswith('_t') and cls(mat)=='tree_wall']
    if not ks:return verge
    k0,k1=min(ks)-20,max(ks)+20
    candidates=[f for f in faces if not str(f[0]).endswith('_t') and cls(f[0])=='rock' and not str(f[1]).startswith('hf_')]
    nr=geobuf.prep(candidates).nr.view();C=[];M=[]
    for i,(mat,sec,P,UV) in enumerate(candidates):
        if abs(nr[3*i+1])>.5:C.append(_center(P));M.append(origin.get(mat,mat))
    if not C:return verge
    out=[];count=0
    for mat,sec,P,UV in verge:
        c=_center(P);k,_=_nearest(cen,c)
        if sec=='verge' and k0<=k<=k1:
            j,d=_nearest(C,c)
            if d<=reach*reach:mat=M[j];count+=1
        out.append((mat,sec,P,UV))
    log('       verge: %d cells of the forest stretch (slices %d..%d) take the nearest 1995 rock ground tile'%(count,k0,k1))
    return out
