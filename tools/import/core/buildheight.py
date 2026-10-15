"""NumPy-free height/attribute lookup using the unchanged fg_hf native grid."""
import ctypes
import math
from npyio import Arr
from fastround import _buffer
import geobuf


class AttrField:
    """Snapshot f8(n,3,3) triangles and retain their n Python attributes.

    at(x,z) returns the highest height, at(x,z,yref) the nearest height, and
    at2(x,z,yref) its (height, attribute); no hit returns None. Heights are
    ordinary Python doubles. Ties retain native triangle/bucket order.
    """
    def __init__(self,triangles,attributes,cell=8.):
        self.h=None;self.cell=float(cell)
        if not math.isfinite(self.cell) or self.cell<=0:raise ValueError('buildheight: invalid cell size')
        t=_buffer(triangles,'<f8',(3,3),'triangles');self.attr=list(attributes);n=t.shape[0]
        if len(self.attr)!=n:raise ValueError('buildheight: attribute count differs from triangles')
        v=t.view();bounds=[];members=0
        for i in range(n):
            p=v[9*i:9*i+9]
            if any(not math.isfinite(x) or abs(x)>1e50 for x in p):raise ValueError('buildheight: invalid coordinates')
            q=[x/self.cell for x in (min(p[::3]),max(p[::3]),min(p[2::3]),max(p[2::3]))]
            if any(not math.isfinite(x) or abs(x)>=2**60 for x in q):raise ValueError('buildheight: grid coordinates out of range')
            box=tuple(math.floor(x) for x in q);bounds.append(box)
            members+=(box[1]-box[0]+1)*(box[3]-box[2]+1)
            if members>40000000:raise ValueError('buildheight: triangle grid membership too large')
        if bounds:
            self.bounds=(min(b[0] for b in bounds),max(b[1] for b in bounds),min(b[2] for b in bounds),max(b[3] for b in bounds))
            x0,x1,z0,z1=self.bounds
            if (x1-x0+1)*(z1-z0+1)>40000000:raise ValueError('buildheight: grid too large')
        else:self.bounds=(0,-1,0,-1)
        self._T=Arr('<f8',t.shape,bytearray(t.buf));L=geobuf._native();self.L=L;P=ctypes.c_void_p;I=ctypes.c_longlong;D=ctypes.c_double
        L.fg_hf_build.argtypes=[P,I,D];L.fg_hf_build.restype=P
        L.fg_hf_free.argtypes=[P];L.fg_hf_free.restype=None
        L.fg_hf_at.argtypes=[P,D,D,D,ctypes.c_int,P];L.fg_hf_at.restype=I
        self.h=L.fg_hf_build(self._T.ptr(),n,self.cell)
        if not self.h:raise ValueError('buildheight: native grid allocation failed')

    @classmethod
    def from_records(cls,records,cell=8.):
        records=list(records);X,off,lens=geobuf.pack([p for a,p in records],col=None)
        if any(n!=3 for n in lens.view()):raise ValueError('buildheight: records must be triangles')
        return cls(Arr('<f8',(len(records),3,3),X.buf),[a for a,p in records],cell)

    def _query(self,x,z,yref):
        if not self.h:raise ValueError('buildheight: field is closed')
        x=float(x);z=float(z);yref=None if yref is None else float(yref)
        if not math.isfinite(x) or not math.isfinite(z) or (yref is not None and not math.isfinite(yref)):raise ValueError('buildheight: nonfinite query')
        qx=x/self.cell;qz=z/self.cell
        if not math.isfinite(qx) or not math.isfinite(qz):return None
        cx,cz=math.floor(qx),math.floor(qz);x0,x1,z0,z1=self.bounds
        if not (x0<=cx<=x1 and z0<=cz<=z1):return None
        y=ctypes.c_double();i=self.L.fg_hf_at(self.h,x,z,0. if yref is None else yref,int(yref is None),ctypes.byref(y))
        return None if i<0 else (y.value,self.attr[i])

    def at(self,x,z,yref=None):
        hit=self._query(x,z,yref)
        return None if hit is None else hit[0]

    def at2(self,x,z,yref):return self._query(x,z,yref)

    def close(self):
        if self.h:self.L.fg_hf_free(self.h);self.h=None

    def __enter__(self):
        if not self.h:raise ValueError('buildheight: field is closed')
        return self

    def __exit__(self,*exc):self.close()

    def __del__(self):
        try:self.close()
        except Exception:pass
