"""NumPy-free oriented polygon normals and weighted corner-normal tables."""
import ctypes
import math
import geobuf
from npyio import Arr
from fastround import _buffer


def _geometry(polygons):
    X,off,lens=geobuf.pack(polygons,None);x=X.view();o=off.view();w=[];c=[];low=[]
    if any(not math.isfinite(v) or abs(v)>1e12 for v in x):raise ValueError('buildnormals: invalid coordinate')
    for f,k in enumerate(lens.view()):
        if not k:raise ValueError('buildnormals: empty polygon')
        P=[tuple(x[3*i:3*i+3]) for i in range(o[f],o[f+1])]
        sums=list(P[0]);nw=None
        for i,a in enumerate(P):
            b=P[(i+1)%k]
            t=[(a[1]-b[1])*(a[2]+b[2]),(a[2]-b[2])*(a[0]+b[0]),(a[0]-b[0])*(a[1]+b[1])]
            nw=t if nw is None else [nw[d]+t[d] for d in range(3)]
            if i:sums=[sums[d]+a[d] for d in range(3)]
        w.append(nw);c.append([v/k for v in sums]);low.append(min(p[1] for p in P))
    return X,off,lens,w,c,low


def _orient(w,c,low,road,ground):
    road=_buffer(road,'<f8',(2,),'road points');rv=road.view()
    if any(not math.isfinite(v) or abs(v)>1e12 for v in rv):raise ValueError('buildnormals: invalid road point')
    n=[];up=[]
    for i,(x,y,z) in enumerate(w):
        length=max(math.sqrt((x*x+y*y)+z*z),1e-12);v=[x/length,y/length,z/length]
        if abs(v[1])>.3:
            if v[1]<0:v=[-a for a in v]
        else:up.append(i)
        n.append(v)
    if ground is not None and up:
        a=[Arr('<f8',(len(up),)) for _ in range(3)];b=[Arr('<f8',(len(up),)) for _ in range(3)]
        av=[v.view() for v in a];bv=[v.view() for v in b]
        for j,i in enumerate(up):
            h=max(math.sqrt(n[i][0]*n[i][0]+n[i][2]*n[i][2]),1e-9);hx=n[i][0]/h;hz=n[i][2]/h
            av[0][j]=c[i][0]+2.*hx;av[1][j]=c[i][2]+2.*hz;av[2][j]=low[i]
            bv[0][j]=c[i][0]-2.*hx;bv[1][j]=c[i][2]-2.*hz;bv[2][j]=low[i]
        ya=_buffer(ground(*a),'<f8',(),'ground heights');yb=_buffer(ground(*b),'<f8',(),'ground heights')
        if ya.shape!=(len(up),) or yb.shape!=ya.shape:raise ValueError('buildnormals: ground count mismatch')
        rest=[]
        for i,y1,y2 in zip(up,ya.view(),yb.view()):
            ha=y1>-900.;hb=y2>-900.
            if hb and (not ha or y2>y1+.3):n[i]=[-v for v in n[i]]
            if (not ha and not hb) or (ha and hb and abs(y1-y2)<=.3):rest.append(i)
        up=rest
    if up:
        if not road.shape[0]:raise ValueError('buildnormals: upright faces require road points')
        pts=Arr('<f8',(len(up),2));pv=pts.view();ix=Arr('<i8',(len(up),))
        for j,i in enumerate(up):pv[2*j]=c[i][0];pv[2*j+1]=c[i][2]
        L=geobuf._native();L.fg_argmin2.argtypes=[ctypes.c_void_p,ctypes.c_longlong,ctypes.c_void_p,ctypes.c_longlong,ctypes.c_void_p];L.fg_argmin2.restype=None
        L.fg_argmin2(pts.ptr(),len(up),road.ptr(),road.shape[0],ix.ptr())
        for i,k in zip(up,ix.view()):
            dx=rv[2*k]-c[i][0];dz=rv[2*k+1]-c[i][2]
            if n[i][0]*dx+n[i][2]*dz<0.:n[i]=[-v for v in n[i]]
    return n


def oriented_normals(polygons,road,ground=None):
    """f8(n,3) normals; ground(x,z,base) receives/returns f8(n) Arrs.

    Explicit road points and optional ground callback replace module globals.
    The callback is invoked on positive then negative sides in polygon order.
    Existing fastbuild/build_classic APIs are not installed or changed.
    """
    X,off,lens,w,c,low=_geometry(polygons);n=_orient(w,c,low,road,ground)
    out=Arr('<f8',(len(n),3));v=out.view()
    for i,row in enumerate(n):
        for d in range(3):v[3*i+d]=row[d]
    return out


def _round_cm(x):
    value=round(x*100.)/100.
    return math.copysign(0.,x) if value==0. else value


def smooth_normals(faces,road,ground=None):
    """Insertion-ordered corner -> normal tuples, preserving accumulation order."""
    X,off,lens,w,c,low=_geometry([fc[2] for fc in faces]);n=_orient(w,c,low,road,ground);x=X.view();o=off.view();acc={}
    # fastbuild first orients, then falls back to the original whole function
    # outside its packed-key range. The original orients again (callbacks too).
    if any(abs(round(_round_cm(v)*100.))>=1<<20 for v in x):
        n=_orient(w,c,low,road,ground)
    for i,(wx,wy,wz) in enumerate(w):
        ar=math.sqrt((wx*wx+wz*wz)+wy*wy);weight=[v*ar for v in n[i]]
        for k in range(o[i],o[i+1]):
            key=tuple(_round_cm(x[3*k+d]) for d in range(3));old=acc.get(key,(0.,0.,0.))
            acc[key]=tuple(old[d]+weight[d] for d in range(3))
    out={}
    for key,(x,y,z) in acc.items():
        length=max(math.sqrt((x*x+z*z)+y*y),1e-12);out[key]=(x/length,y/length,z/length)
    return out
