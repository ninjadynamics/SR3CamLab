"""Owned NumPy-free wrapper for fastbuild.Near's existing native ring search."""
import ctypes
import math
from npyio import Arr
from fastround import _buffer
import geobuf


def _points(a,cell,name):
    a=_buffer(a,'<f8',(2,),name)
    for v in a.view():
        q=v/cell
        if not math.isfinite(v) or abs(v)>1e150 or not math.isfinite(q) or abs(q)>=2**60:
            raise ValueError('buildnear: coordinates outside bounded native grid')
    return a


class Near:
    """Index f8(n,2) Arr points; calls return owned Windows-int i4(m) Arrs.

    Construction snapshots its input so later changes cannot invalidate the
    native bucket grid. The snapshot lives as long as the handle. Search ties,
    the 200-cell search limit and empty-index zero results match fastbuild.Near.
    """
    def __init__(self,points,cell=8.):
        self.h=None;self.cell=float(cell)
        if not math.isfinite(self.cell) or self.cell<=0:raise ValueError('buildnear: invalid cell size')
        points=_points(points,self.cell,'points');n=points.shape[0]
        if n>=1<<31:raise ValueError('buildnear: too many points for i4 result')
        v=points.view()
        if n:
            xs=[math.floor(x/self.cell) for x in v[::2]];zs=[math.floor(z/self.cell) for z in v[1::2]]
            if (max(xs)-min(xs)+1)*(max(zs)-min(zs)+1)>40000000:raise ValueError('buildnear: grid too large')
        self._P=Arr('<f8',points.shape,bytearray(points.buf))
        L=geobuf._native();self.L=L;P=ctypes.c_void_p;I=ctypes.c_longlong
        L.fg_init2.argtypes=[];L.fg_init2.restype=ctypes.c_int
        if not L.fg_init2():raise RuntimeError('buildnear: UCRT hypot unavailable')
        L.fg_near_build.argtypes=[P,I,ctypes.c_double];L.fg_near_build.restype=P
        L.fg_near_free.argtypes=[P];L.fg_near_free.restype=None
        L.fg_near_query.argtypes=[P,P,I,P];L.fg_near_query.restype=None
        self.h=L.fg_near_build(self._P.ptr(),n,self.cell)
        if not self.h:raise ValueError('buildnear: native grid allocation failed')

    def __call__(self,queries):
        if not self.h:raise ValueError('buildnear: index is closed')
        q=_points(queries,self.cell,'queries');m=q.shape[0];wide=Arr('<i8',(m,));out=Arr('<i4',(m,))
        if m:self.L.fg_near_query(self.h,q.ptr(),m,wide.ptr())
        ov=out.view()
        for i,k in enumerate(wide.view()):ov[i]=k
        return out

    def close(self):
        if self.h:self.L.fg_near_free(self.h);self.h=None

    def __enter__(self):
        if not self.h:raise ValueError('buildnear: index is closed')
        return self

    def __exit__(self,*exc):self.close()

    def __del__(self):
        try:self.close()
        except Exception:pass
