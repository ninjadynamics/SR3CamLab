"""Plain-number surface subdivision and UV mapping, matching retex's float64 steps.

Inputs are finite point rows; outputs are owned lists of coordinate tuples.
The grid cap deliberately preserves the original aspect-ratio scaling, which
can leave more than 400 pieces for a very long narrow face.
"""
import math
from npexact import ddot


def _points(q):
    q=[tuple(map(float,p)) for p in q]
    if len(q)<3 or any(len(p)!=3 for p in q):raise ValueError('retexuv: at least three 3D corners required')
    if any(not math.isfinite(v) or abs(v)>1e50 for p in q for v in p):raise ValueError('retexuv: nonfinite or oversized coordinate')
    return q


def _cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def _sub(a,b):return tuple(a[k]-b[k] for k in range(3))
def _norm(a):return math.sqrt(ddot(a,a))
def _dot(a,b):return ddot(a,b)
def _normal(q):return _cross(_sub(q[1],q[0]),_sub(q[2],q[0]))
def _positive(x,name):
    x=float(x)
    if not math.isfinite(x) or x<=0:raise ValueError('retexuv: positive finite '+name+' required')
    return x


def subdivide(P,maxlen):
    """Four corners -> bilinear quads in i/j order; repeated corner for triangles."""
    P=_points(P);maxlen=_positive(maxlen,'maxlen')
    if len(P)!=4:raise ValueError('retexuv: subdivision requires four corners')
    lu=max(_norm(_sub(P[1],P[0])),_norm(_sub(P[2],P[3])))
    lv=max(_norm(_sub(P[3],P[0])),_norm(_sub(P[2],P[1])))
    if not math.isfinite(lu/maxlen) or not math.isfinite(lv/maxlen):raise ValueError('retexuv: excessive subdivision count')
    n=max(1,math.ceil(lu/maxlen));m=max(1,math.ceil(lv/maxlen))
    if n*m>400:
        s=math.sqrt(400.0/(n*m));n=max(1,int(n*s));m=max(1,int(m*s))
    if n*m>1000000:raise ValueError('retexuv: excessive grid allocation')
    def pt(a,b):return tuple((P[0][k]*(1-a)+P[1][k]*a)*(1-b)+(P[3][k]*(1-a)+P[2][k]*a)*b for k in range(3))
    return [[pt(i/n,j/m),pt((i+1)/n,j/m),pt((i+1)/n,(j+1)/m),pt(i/n,(j+1)/m)] for i in range(n) for j in range(m)]


def tree_uv(P,min_h=2.5,aspect=4.0,vtop=.13,vbot=.895):
    """Upright foliage board -> (quad,UV), or None below the orientation/height limits."""
    q=_points(P)
    if len(q)!=4:q=q+[q[2]]
    aspect=_positive(aspect,'aspect');min_h=float(min_h);vtop=float(vtop);vbot=float(vbot)
    if not all(math.isfinite(v) for v in (min_h,vtop,vbot)):raise ValueError('retexuv: finite tree parameters required')
    n=_normal(q);ln=_norm(n)
    if ln<1e-9 or abs(n[1]/ln)>.35:return None
    y0=min(p[1] for p in q);y1=max(p[1] for p in q);H=y1-y0
    if H<min_h:return None
    h=(-n[2],0.,n[0]);l=_norm(h);h=tuple(v/l for v in h)
    s=[_dot(p,h) for p in q];lo=min(s);s=[v-lo for v in s];W=max(max(s),1e-6)
    span=min(1.9,W/H*(vbot-vtop)/aspect)
    u0=(abs(q[0][0]*.137+q[0][2]*.291)%1.)*(1.99-span)
    uv=[(u0+a/W*span,vbot-(p[1]-y0)/H*(vbot-vtop)) for a,p in zip(s,q)]
    return q,uv


def _shift(uv,repeat):
    repeat=_positive(repeat,'repeat');uv=[(u/repeat,v/repeat) for u,v in uv]
    lo=[math.floor(min(p[k] for p in uv)+1e-6) for k in range(2)]
    # NumPy's maximum chooses its second argument on a tie, clearing -0.0.
    def clip(v):return 0. if v<=0. else 1.999 if v>=1.999 else v
    return [tuple(clip(p[k]-lo[k]) for k in range(2)) for p in uv]


def plane_uv(q,repeat=3.0):
    """World-anchored UVs along a surface's horizontal direction and slope."""
    q=_points(q);n=_normal(q);ln=_norm(n)
    if ln<1e-9:return box_uv(q,repeat)
    n=tuple(v/ln for v in n)
    if abs(n[1])>.92:uv=[(p[0],p[2]) for p in q]
    else:
        h=(n[2],0.,-n[0]);l=_norm(h);h=tuple(v/l for v in h)
        k=0 if abs(h[0])>abs(h[2]) else 2
        if h[k]<=0:h=tuple(-v for v in h)
        t=_cross(n,h)
        if t[1]<=0:t=tuple(-v for v in t)
        uv=[(_dot(p,h),-_dot(p,t)) for p in q]
    return _shift(uv,repeat)


def box_uv(q,repeat=3.0):
    """Project on the normal's dominant axis, shifting and clamping into 0..1.999."""
    q=_points(q);n=_normal(q);a=max(range(3),key=lambda k:abs(n[k])) if _norm(n)>1e-9 else 1
    uv=[(p[0],p[2]) if a==1 else (p[2] if a==0 else p[0],-p[1]) for p in q]
    return _shift(uv,repeat)
