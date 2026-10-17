"""Additive NumPy-free verge and slope generation for f8 road buffers."""
import collections
import ctypes
import math
import fillboards
import fillbuf
import fillroad
import geobuf
from fastround import _buffer
from npexact import ddot

_crt=ctypes.CDLL('ucrtbase');_hypot=_crt.hypot
_hypot.argtypes=[ctypes.c_double,ctypes.c_double];_hypot.restype=ctypes.c_double


def _area(P):
    a=[float(P[1][j])-float(P[0][j]) for j in range(3)];b=[float(P[2][j])-float(P[0][j]) for j in range(3)]
    c=[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]]
    return math.sqrt(ddot(c,c))


def label_tile(faces,labels,classes=('grass','rock')):
    """Largest lying tile in the first available class; labels are explicit."""
    if labels is None:return None
    nr=geobuf.prep(faces).nr.view();area=collections.Counter()
    for i,(mat,sec,P,UV) in enumerate(faces):
        if labels.get(mat) in classes and abs(nr[3*i+1])>.5:area[mat]+=_area(P)
    for cls in classes:
        best=[mat for mat,a in area.most_common() if labels[mat]==cls]
        if best:return best[0]
    return None


def ground_skirts(faces,rd,tile_alpha,sea=-.5,slopes=False,reach=30.,drop=14.,tile=None,clear=10.,labels=None):
    """Return (faces, skirt_info, hanging_tile_counts), without global updates.

    V and lat must be f8 Arrs; code and width buffers follow fillroad. This
    matches the collected production road type. Other floating types fail
    explicitly rather than changing the intermediate arithmetic silently.
    """
    hw,V,n,B=fillroad._inputs(rd)
    if V.dtype!='<f8':raise ValueError('fillskirts: V must use f8')
    lat=_buffer(rd['lat'],'<f8',(3,),'lat')
    if lat.shape!=(n,3):raise ValueError('fillskirts: lateral count differs from road')
    road=fillroad.road_faces(rd);code=rd['code'].view();v=V.view();lv=lat.view()
    if any(not math.isfinite(x) for x in v) or any(not math.isfinite(x) for x in lv):raise ValueError('fillskirts: nonfinite road')
    cen=[tuple(v[3*(k*B+hw):3*(k*B+hw)+3]) for k in range(n)]
    def point(k,c):return list(v[3*(k*B+c):3*(k*B+c)+3])
    def lateral(k):return lv[3*k:3*k+3]
    allf=list(faces)+road;hang,tiles=fillboards.hanging_boards(allf,tile_alpha,1.)
    want=[[False,False] for _ in range(n)]
    for fi,i,j in hang:
        b=[(float(allf[fi][2][i][a])+float(allf[fi][2][j][a]))/2. for a in range(3)]
        k=min(range(n),key=lambda k:_hypot(cen[k][0]-b[0],cen[k][2]-b[2]))
        s=ddot([b[a]-cen[k][a] for a in range(3)],lateral(k),k%2)
        if abs(s)<hw+reach:
            for t in range(-3,4):want[(k+t)%n][int(s>0)]=True
    tile=tile or label_tile(faces,labels)
    if tile is None:
        nr=geobuf.prep(faces).nr.view();area=collections.Counter()
        for i,(mat,sec,P,UV) in enumerate(faces):
            if not (mat.endswith('_t') or mat.startswith('col_')) and abs(nr[3*i+1])>.5:area[mat]+=_area(P)
        tile=area.most_common(1)[0][0] if area else None
    if tile is None:return [],dict(added=0),tiles
    out=[];c0,c1=fillroad.strip(rd);c0,c1=c0.view(),c1.view();why=collections.Counter()
    ok=[[False,False] for _ in range(n)];A=[[[0.,0.,0.] for _ in range(2)] for _ in range(n)];Bp=[[[0.,0.,0.] for _ in range(2)] for _ in range(n)]
    def append_face(section,P,UV):
        if geobuf.prep([P],col=None).nr.view()[1]<0:P=P[::-1];UV=UV[::-1]
        out.append((tile,section,[tuple(q) for q in P],UV))
    with fillbuf.Index(faces) as ix:
        for k in range(n):
            k2=(k+1)%n
            for sd in (0,1):
                if not (want[k][sd] or want[k2][sd]):continue
                cols=range(max(c1[k],c1[k2]),B-1) if sd else range(min(c0[k],c0[k2])-1,-1,-1)
                for c in cols:
                    if min(code[k*B+c],code[k*B+c+1],code[k2*B+c],code[k2*B+c+1])<0:break
                    Q=[point(k,c),point(k,c+1),point(k2,c+1),point(k2,c)];m=[sum(q[a] for q in Q)/4. for a in range(3)]
                    if any(abs(y-m[1])<3. for y,f in ix.heights(m[0],m[2])):continue
                    for q in Q:q[1]-=.05
                    UV=[((c%8)/8.,(k%8)/8.),((c%8+1)/8.,(k%8)/8.),((c%8+1)/8.,(k%8+1)/8.),((c%8)/8.,(k%8+1)/8.)]
                    append_face('verge',Q,UV)
        nverge=len(out)
        for k in range(n if slopes else 0):
            for sd in (0,1):
                if not want[k][sd]:continue
                step=1 if sd else -1;c=hw
                while 0<=c+step<B and code[k*B+c+step]>=0:c+=step
                l=[x*step for x in lateral(k)];e=point(k,c)
                if e[1]-sea<1.:why['at sea level']+=1;continue
                a=[e[j]+l[j]*.3 for j in range(3)];a[1]=e[1]-.15
                b=[a[j]+l[j]*reach for j in range(3)];b[1]=max(sea-.5,e[1]-drop)
                pts=[[a[j]+(b[j]-a[j])*(1. if t==8 else t*((1.-.02)/8.)+.02) for j in range(3)] for t in range(9)]
                if any(ix.heights(q[0],q[2]) for q in pts):why['geometry there']+=1;continue
                far=[c for c in range(n) if abs((c-k+n//2)%n-n//2)>25]
                if not far:raise ValueError('fillskirts: no far road points for slope clearance')
                if any(min(_hypot(cen[c][0]-q[0],cen[c][2]-q[2]) for c in far)<clear for q in pts):why['other road near']+=1;continue
                ok[k][sd]=True;A[k][sd]=a;Bp[k][sd]=b
    nrun=0
    for sd in (0,1):
        link=[]
        for k in range(n):
            k2=(k+1)%n;da=[A[k2][sd][j]-A[k][sd][j] for j in range(3)];db=[Bp[k2][sd][j]-Bp[k][sd][j] for j in range(3)]
            link.append(ok[k][sd] and ok[k2][sd] and ddot(db,da)>0 and math.sqrt(ddot(da,da))<6.)
        k=0
        while k<n:
            if not link[k]:k+=1;continue
            e=k
            while e<n and link[e]:e+=1
            if e-k>=2:
                nrun+=1
                for q in range(k,e):
                    q2=(q+1)%n;a0,b0,a1,b1=A[q][sd],Bp[q][sd],A[q2][sd],Bp[q2][sd]
                    m0=[(a0[j]+b0[j])/2. for j in range(3)];m1=[(a1[j]+b1[j])/2. for j in range(3)]
                    u0=((q-k)%8)/8.;u1=u0+1/8.
                    for P,v0,v1 in (([a0,a1,m1,m0],0.,.5),([m0,m1,b1,b0],.5,1.)):
                        append_face('skirt',P,[(u0,v0),(u1,v0),(u1,v1),(u0,v1)])
            k=e
    info=dict(added=len(out),verge_cells=nverge,slope_quads=len(out)-nverge,runs=nrun,slice_sides_ok=sum(sum(r) for r in ok),wanted=sum(sum(r) for r in want),skipped=dict(why),tile=tile)
    return out,info,tiles
