"""Additive NumPy-free UV preparation and packing for mesh construction."""
import math
from npyio import Arr
from fastround import _buffer


def mesh_uv(faces,uv_mode):
    """Return f8(n,4,3) quads, f8(n,4,2) repeats and clamped-face count.

    Matches fastbuild.mesh_uv on finite face records. Unsupported corner/UV
    layouts return None for the caller's fallback. Inputs remain untouched.
    """
    data=[]
    try:
        for fc in faces:
            P,U=fc[2:4]
            if len(P)<3 or len(U)!=len(P):return None
            if any(len(p)!=3 for p in P) or any(len(u)!=2 for u in U):return None
            P=[tuple(map(float,p)) for p in P];U=[tuple(map(float,u)) for u in U]
            data.append((P,U))
    except (ValueError,TypeError,IndexError):return None
    if any(not math.isfinite(x) for pair in data for A in pair for p in A for x in p):
        raise ValueError('buildmesh: finite coordinates required')
    Q=Arr('<f8',(len(data),4,3));uv=Arr('<f8',(len(data),4,2));qv=Q.view();v=uv.view();clamp=0
    for f,(P,U) in enumerate(data):
        ix=(0,1,2,2 if len(P)==3 else 3)
        U=[list(U[k]) for k in ix]
        for c,k in enumerate(ix):
            for d in range(3):qv[f*12+c*3+d]=P[k][d]
        if uv_mode=='tile':
            for u in U:u[1]=1.-u[1]
            shift=[math.floor(min(u[d] for u in U)+1e-6) for d in range(2)]
            U=[[u[d]-shift[d] for d in range(2)] for u in U]
            if max(x for u in U for x in u)>1.999:
                clamp+=1
                U=[[0. if x<=0. else 1.999 if x>=1.999 else x for x in u] for u in U]
        elif uv_mode!='given':U=[[0.,0.],[1.,0.],[1.,1.],[0.,1.]]
        over=[1. if max(u[d] for u in U)>1.00002 else 0. for d in range(2)]
        for c,u in enumerate(U):
            for d in range(2):v[f*8+c*2+d]=u[d]-over[d]
    return Q,uv,clamp


def pack_uv(u):
    """Checked f8(n,4,2) repeats -> u2(4*n,2), NumPy ties-to-even rounding."""
    u=_buffer(u,'<f8',(4,2),'uv');out=Arr('<u2',(4*u.shape[0],2));v=out.view()
    for i,x in enumerate(u.view()):
        if not math.isfinite(x):raise ValueError('buildmesh: finite UV required')
        x=x*32768.
        # Clipping first is equivalent here, including overflowing finite inputs.
        x=-32768 if x<=-32768 else 32767 if x>=32767 else round(x)
        v[i]=int(x)&65535
    return out
