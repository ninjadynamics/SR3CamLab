"""NumPy-free application of a snapshotted corner-normal table."""
import math
from npyio import Arr
from fastround import _buffer
from npexact import ddot


class Smooth:
    """Snapshot the table; apply returns owned f8(n,3) normals.

    Finite f4(n,3|4) positions and f8(n,3) normals are checked and borrowed.
    Mirrors fastbuild.apply_smooth's first quantized-key match and global
    large-coordinate fallback. Rebuild this object when the table changes.
    Legacy NumPy entry points and their in-place/cache contracts are unchanged.
    """
    def __init__(self,table):
        self.table={};self.keys={};self.big=False
        for key,value in table.items():
            if len(key)!=3 or len(value)!=3:raise ValueError('buildsmooth: triples required')
            key=tuple(map(float,key));value=tuple(map(float,value))
            if any(not math.isfinite(x) or abs(x)>1e12 for x in key) or any(not math.isfinite(x) for x in value):
                raise ValueError('buildsmooth: invalid table value')
            nk=tuple(round(x*100.) for x in key)
            self.big|=any(abs(x)>=1<<20 for x in nk)
            self.table[key]=value;self.keys.setdefault(nk,value)

    def apply(self,normals,positions):
        normals=_buffer(normals,'<f8',(3,),'normals')
        if not isinstance(positions,Arr) or len(positions.shape)!=2 or positions.shape[1] not in (3,4):
            raise ValueError('buildsmooth: positions must be f4(n,3|4)')
        positions=_buffer(positions,'<f4',(positions.shape[1],),'positions')
        if normals.shape[0]!=positions.shape[0]:raise ValueError('buildsmooth: vertex counts differ')
        if any(not math.isfinite(x) for x in normals.view()):raise ValueError('buildsmooth: finite normals required')
        out=Arr('<f8',normals.shape,bytearray(normals.buf))
        if not self.table or not normals.shape[0]:return out
        stride=positions.shape[1];pv=positions.view();rounded=[];codes=[];big=self.big
        for i in range(positions.shape[0]):
            p=tuple(pv[i*stride+d] for d in range(3))
            if any(not math.isfinite(x) or abs(x)>1e12 for x in p):raise ValueError('buildsmooth: invalid position')
            p=tuple(round(x*100.)/100. for x in p);nk=tuple(round(x*100.) for x in p)
            rounded.append(p);codes.append(nk);big|=any(abs(x)>=1<<20 for x in nk)
        nv=out.view()
        for i in range(normals.shape[0]):
            q=self.table.get(rounded[i]) if big else self.keys.get(codes[i])
            if q is None:continue
            v=tuple(nv[i*3:i*3+3])
            dot=ddot(q,v,i%2) if big else (q[0]*v[0]+q[1]*v[1])+q[2]*v[2]
            for d in range(3):nv[i*3+d]=q[d] if dot>=0. else -q[d]
        return out
