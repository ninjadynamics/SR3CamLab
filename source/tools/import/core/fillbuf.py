"""Additive NumPy-free fill1995 geometry index, backed by the existing C grid.

Index(faces, cell=8).heights/uprights return lists of ordinary Python numbers
in the same order as fastgeo.IndexC. No legacy callers or scalar types change.
The object owns its native grid; close() and the context manager release it.
"""
import ctypes
import math
from npyio import Arr
import geobuf


class Index:
    def __init__(self,faces,cell=8.0):
        self.h=None;self.cell=float(cell)
        if not math.isfinite(self.cell) or self.cell<=0:raise ValueError('fillbuf: cell must be positive and finite')
        g=geobuf.prep(faces)
        if any(k<1 for k in g.lens.view()):raise ValueError('fillbuf: polygons need at least one corner')
        if any(not math.isfinite(v) or abs(v)>1e50 for v in g.X.view()):raise ValueError('fillbuf: coordinates must be finite and bounded')
        if any(not math.isfinite(v) for v in g.nr.view()):raise ValueError('fillbuf: nonfinite normals')
        # Bound the old native grid before its int64 casts and dimension product.
        # Include the upright-segment expansion, even for lying polygons.
        if g.n:
            lo=g.lo.view();hi=g.hi.view()
            bounds=(min(lo[0::3])-.6,min(lo[2::3])-.6,max(hi[0::3])+.6,max(hi[2::3])+.6)
            q=[v/self.cell for v in bounds]
            if any(not math.isfinite(v) or abs(v)>=2**60 for v in q):raise ValueError('fillbuf: grid coordinates out of range')
            self.bounds=tuple(math.floor(v) for v in q)
            x0,z0,x1,z1=self.bounds
            if (x1-x0+1)*(z1-z0+1)>40000000:raise ValueError('fillbuf: grid too large')
        else:self.bounds=(0,0,-1,-1)
        L=geobuf._native();self.L=L;P=ctypes.c_void_p;I=ctypes.c_longlong;D=ctypes.c_double
        L.fg_index_build.argtypes=[P,P,I,P,P,D];L.fg_index_build.restype=P
        L.fg_index_free.argtypes=[P];L.fg_index_free.restype=None
        L.fg_index_counts.argtypes=[P,ctypes.c_int];L.fg_index_counts.restype=I
        for name in ('fg_index_segs','fg_index_segfi','fg_index_segcut'):
            f=getattr(L,name);f.argtypes=[P];f.restype=P
        L.fg_index_heights.argtypes=[P,D,D,ctypes.c_int,P,P,I];L.fg_index_heights.restype=I
        L.fg_index_uprights.argtypes=[P,D,D,D,P,I];L.fg_index_uprights.restype=I
        cut=Arr('|u1',(g.n,),bytearray(f[0].endswith('_t') for f in faces))
        self.h=L.fg_index_build(g.X.ptr(),g.off.ptr(),g.n,g.nr.ptr(),cut.ptr(),self.cell)
        if not self.h:raise ValueError('fillbuf: grid allocation failed or too large')
        try:
            ns=L.fg_index_counts(self.h,1)
            raw=ctypes.string_at(L.fg_index_segs(self.h),48*ns)
            seg=memoryview(raw).cast('d')
            self.sy0=list(seg[4::6]);self.sy1=list(seg[5::6])
            self.sfi=list(memoryview(ctypes.string_at(L.fg_index_segfi(self.h),8*ns)).cast('q'))
            self.scut=[bool(v) for v in ctypes.string_at(L.fg_index_segcut(self.h),ns)]
            self._grow(512)
        except BaseException:
            self.close();raise

    def _grow(self,cap):
        self.cap=cap;self.oy=Arr('<f8',(cap,));self.ofi=Arr('<i8',(cap,))

    def close(self):
        if self.h:self.L.fg_index_free(self.h);self.h=None

    def __del__(self):
        try:self.close()
        except Exception:pass

    def __enter__(self):
        if not self.h:raise ValueError('fillbuf: index is closed')
        return self

    def __exit__(self,*exc):self.close()

    def _query(self,x,z):
        if not self.h:raise ValueError('fillbuf: index is closed')
        x=float(x);z=float(z)
        if not math.isfinite(x) or not math.isfinite(z):raise ValueError('fillbuf: query coordinates must be finite')
        a=x/self.cell;b=z/self.cell
        if not math.isfinite(a) or not math.isfinite(b):return None
        a=math.floor(a);b=math.floor(b);x0,z0,x1,z1=self.bounds
        return (x,z) if x0<=a<=x1 and z0<=b<=z1 else None

    def heights(self,x,z,opaque_only=False):
        q=self._query(x,z)
        if q is None:return []
        f=self.L.fg_index_heights
        m=f(self.h,*q,bool(opaque_only),self.oy.ptr(),self.ofi.ptr(),self.cap)
        if m<0:
            self._grow(-m*2);m=f(self.h,*q,bool(opaque_only),self.oy.ptr(),self.ofi.ptr(),self.cap)
        return list(zip(self.oy.view()[:m],self.ofi.view()[:m]))

    def uprights(self,x,z,r=.5):
        q=self._query(x,z);r=float(r)
        if not math.isfinite(r) or r<0:raise ValueError('fillbuf: radius must be finite and nonnegative')
        if q is None:return []
        f=self.L.fg_index_uprights;m=f(self.h,*q,r,self.ofi.ptr(),self.cap)
        if m<0:
            self._grow(-m*2);m=f(self.h,*q,r,self.ofi.ptr(),self.cap)
        return [(self.sy0[k],self.sy1[k],self.sfi[k],self.scut[k]) for k in self.ofi.view()[:m]]
