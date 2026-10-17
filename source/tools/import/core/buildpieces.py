"""NumPy-free face grids, preserving fastbuild's grouped callback order."""
import math
from npyio import Arr
from fastround import _buffer


def pieces(faces, maxlen, hfun=None, lift=0.0):
    """Return interpolated quads, or None for unsupported face layout.

    hfun receives one writable f8(N,3) Arr per sorted (n,m) grid group and
    returns f8(N) Arr heights. This includes repeated/shared grid points,
    in input-face then i then j order, exactly as fastbuild._pieces.
    Result records contain ordinary Python floats. Inputs are not modified.
    Nonfinite geometry/parameters and excessive grid allocations are rejected.
    """
    if not len(faces): return []
    maxlen=float(maxlen);lift=float(lift)
    if not math.isfinite(maxlen) or maxlen<=0 or not math.isfinite(lift):
        raise ValueError('buildpieces: finite positive maxlen and finite lift required')
    quads=[]
    try:
        for fc in faces:
            P,U=fc[2:4]
            if len(P)<3 or len(U)!=len(P): return None
            if any(len(p)!=3 for p in P) or any(len(u)!=2 for u in U): return None
            P=[tuple(map(float,p)) for p in P];U=[tuple(map(float,u)) for u in U]
            quads.append((P,U))
    except (ValueError,TypeError,IndexError): return None
    if any(not math.isfinite(x) or abs(x)>1e50 for pair in quads for A in pair for p in A for x in p):
        raise ValueError('buildpieces: nonfinite or oversized coordinate')
    groups={};total=0
    for f,(P,U) in enumerate(quads):
        ix=(0,1,2,2 if len(P)==3 else 3);P=[P[k] for k in ix];U=[U[k] for k in ix];quads[f]=(P,U)
        def length(a,b):
            x,y,z=(P[a][k]-P[b][k] for k in range(3))
            return math.sqrt((x*x+z*z)+y*y)
        du=max(length(1,0),length(2,3))/maxlen;dv=max(length(3,0),length(2,1))/maxlen
        if not math.isfinite(du) or not math.isfinite(dv) or max(du,dv)>=2**31:
            raise ValueError('buildpieces: excessive subdivision count')
        n=max(1,math.ceil(du));m=max(1,math.ceil(dv))
        if n*m>900:
            sc=(900.0/(n*m))**0.5;n=max(1,int(n*sc));m=max(1,int(m*sc))
        total+=(n+1)*(m+1)
        if n>=100000 or m>=100000 or total>10000000:
            raise ValueError('buildpieces: excessive grid allocation')
        groups.setdefault((n,m),[]).append(f)
    result=[None]*len(faces)
    for (n,m),ff in sorted(groups.items()):
        stride=(n+1)*(m+1);points=Arr('<f8',(len(ff)*stride,3));pv=points.view();tex=[]
        def point(A,a,b):
            return tuple((A[0][k]*(1-a)+A[1][k]*a)*(1-b)+(A[3][k]*(1-a)+A[2][k]*a)*b for k in range(len(A[0])))
        q=0
        for f in ff:
            P,U=quads[f]
            for i in range(n+1):
                a=i/n
                for j in range(m+1):
                    b=j/m
                    for x in point(P,a,b):pv[q]=x;q+=1
                    tex.append(point(U,a,b))
        if hfun is not None:
            heights=_buffer(hfun(points),'<f8',(),'heights')
            if heights.shape!=(len(ff)*stride,): raise ValueError('buildpieces: callback height count differs from grid')
            for q,y in enumerate(heights.view()):pv[3*q+1]=y+lift
        for g,f in enumerate(ff):
            out=[];mat,sec=faces[f][:2]
            for i in range(n):
                for j in range(m):
                    base=g*stride+i*(m+1)+j;corners=(base,base+m+1,base+m+2,base+1)
                    out.append((mat,sec,[tuple(pv[3*k:3*k+3]) for k in corners],[tex[k] for k in corners]))
            result[f]=out
    return [fc for group in result for fc in group]


def split_faces(faces,maxlen):return pieces(faces,maxlen)


def drape(faces,hfun,lift,maxlen=1.0):return pieces(faces,maxlen,hfun,lift)
