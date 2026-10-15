"""Additive NumPy-free light-side ray scores; legacy lightside is unchanged."""
import ctypes
import math
import sys
from array import array

from npyio import Arr
from fastround import _buffer


def _libraries():
    import cbuild
    from geobuf import _native
    L=_native(); P=ctypes.c_void_p; I=ctypes.c_longlong
    L.fg_side_triangles.argtypes=[P,I,P,I,P]; L.fg_side_triangles.restype=I
    L.fg_side_fans.argtypes=[P,P,P,I,P,ctypes.c_double,P,P,P]; L.fg_side_fans.restype=None
    L.fg_side_reduce.argtypes=[P,P,P,P,I,ctypes.c_int,P]; L.fg_side_reduce.restype=None
    R=ctypes.CDLL(cbuild.dll('rays'))
    R.rt_build.argtypes=[P,ctypes.c_int]; R.rt_build.restype=P
    R.rt_free.argtypes=[P]; R.rt_free.restype=None
    R.rt_cast.argtypes=[P,P,P,I,ctypes.c_double,P,P]; R.rt_cast.restype=None
    return L,R


def scores(V,F,ACT):
    """V f8(nv,3), F i8(nf,4), ACT bool(nf) -> owned f4(nf,4) scores.

    Inputs are checked contiguous Arrs. Index ranges are checked before native
    reads. Same triangle ordering, 32-ray fans and capped means as lightside.
    No input is changed. The ray tree is freed even when a batch fails.
    """
    V=_buffer(V,'<f8',(3,),'V'); F=_buffer(F,'<i8',(4,),'F')
    ACT=_buffer(ACT,'|b1',(),'ACT'); nf=F.shape[0]
    if ACT.shape!=(nf,): raise ValueError('sidebuf: face/activity counts differ')
    if nf>min((2**31-1)//2,sys.maxsize//144): raise ValueError('sidebuf: scene too large')
    out=Arr('<f4',(nf,4))
    if not nf: return out
    L,R=_libraries(); nt=L.fg_side_triangles(V.ptr(),V.shape[0],F.ptr(),nf,None)
    if nt<0: raise ValueError('sidebuf: vertex index out of range')
    ids=array('q',(i for i,a in enumerate(ACT.view()) if a))
    if not ids: return out
    T=Arr('<f8',(nt,3,3)); L.fg_side_triangles(V.ptr(),V.shape[0],F.ptr(),nf,T.ptr())
    fan=array('d')
    for k in range(32):
        u=(k+0.5)/32; r=math.sqrt(u)*0.985; a=k*2.399963229728653
        fan.extend((r*math.cos(a),r*math.sin(a),math.sqrt(max(1.0-r*r,0.0))))
    fp=fan.buffer_info()[0]; tree=R.rt_build(T.ptr(),nt)
    if not tree: raise MemoryError('sidebuf: ray tree allocation failed')
    try:
        for start in range(0,len(ids),40000):
            active=ids[start:start+40000]; n=len(active); ap=active.buffer_info()[0]
            org=Arr('<f8',(32*n,3)); direction=Arr('<f8',(32*n,3)); ok=Arr('|u1',(n,))
            hit=Arr('<i4',(32*n,)); dist=Arr('<f8',(32*n,))
            for side,sg in enumerate((1.0,-1.0)):
                L.fg_side_fans(V.ptr(),F.ptr(),ap,n,fp,sg,org.ptr(),direction.ptr(),ok.ptr())
                R.rt_cast(tree,org.ptr(),direction.ptr(),32*n,600.0,hit.ptr(),dist.ptr())
                L.fg_side_reduce(hit.ptr(),dist.ptr(),ok.ptr(),ap,n,side,out.ptr())
    finally: R.rt_free(tree)
    return out
