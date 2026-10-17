"""NumPy-free road proxy faces for fill1995; additive checked-buffer API.

road_faces(rd) accepts V f4/f8(n,b,3), code i4/i8(n,b), integer hw and optional
wl/wr f4/f8(n), all npyio.Arr. Returns ordinary face records. strip(rd) returns
the two i4(n) column limits. Legacy fill1995 callers remain unchanged.
"""
import math
import operator
import struct
from npyio import Arr
from fastround import _buffer

_ROADF=[]
_F32=struct.Struct('<f')
_EPS32=_F32.unpack(_F32.pack(1e-6))[0]


def _float(a,tail,name):
    if not isinstance(a,Arr) or a.dtype not in ('<f4','<f8'):raise ValueError('fillroad: expected floating '+name)
    return _buffer(a,a.dtype,tail,name)


def _inputs(rd):
    hw=operator.index(rd['hw'])
    if not 0<=hw<=(2**31-1)//2:raise ValueError('fillroad: invalid half width')
    v=rd['V']
    if not isinstance(v,Arr) or len(v.shape)!=3 or v.shape[-1]!=3:raise ValueError('fillroad: V must have shape (n,b,3)')
    v=_float(v,v.shape[1:],'V');n,b,_=v.shape
    if b<2*hw+1:raise ValueError('fillroad: road grid narrower than half width')
    return hw,v,n,b


def _limits(rd,hw,n):
    result=[]
    for name,left in (('wl',True),('wr',False)):
        a=rd.get(name)
        if a is None and name in rd:raise ValueError('fillroad: width cannot be None')
        if a is not None:
            a=_float(a,(),name)
            if a.shape!=(n,):raise ValueError('fillroad: width count differs from slices')
            values=a.view();f32=a.dtype=='<f4'
        else:values=None;f32=False
        out=Arr('<i4',(n,));ov=out.view()
        for i in range(n):
            w=float(hw) if values is None else values[i]
            if not math.isfinite(w):raise ValueError('fillroad: widths must be finite')
            value=(-w+_EPS32 if left else w-_EPS32) if f32 else (-w+1e-6 if left else w-1e-6)
            if f32:value=_F32.unpack(_F32.pack(value))[0]
            k=math.floor(value) if left else math.ceil(value)
            if k<-(1<<31) or k>=(1<<31):k=-(1<<31)
            # Windows NumPy int32 addition wraps before clip, too.
            k=((k+hw+(1<<31))%(1<<32))-(1<<31)
            ov[i]=min(max(k,0),2*hw)
        result.append(out)
    return tuple(result)


def strip(rd):
    hw,v,n,b=_inputs(rd)
    return _limits(rd,hw,n)


def road_faces(rd):
    if rd is None:return []
    hw,v,n,b=_inputs(rd);code=rd['code']
    if not isinstance(code,Arr) or code.dtype not in ('<i4','<i8'):raise ValueError('fillroad: expected integer codes')
    code=_buffer(code,code.dtype,(b,),'code')
    if code.shape!=(n,b):raise ValueError('fillroad: code grid differs from V')
    a,z=_limits(rd,hw,n)
    signature=(v.dtype,v.shape,bytes(v.buf),code.dtype,bytes(code.buf),bytes(a.buf),bytes(z.buf))
    if _ROADF and _ROADF[0]==signature:return list(_ROADF[1])
    vv=v.view();cv=code.view();lo=a.view();hi=z.view();out=[]
    for i in range(n):
        j=(i+1)%n
        for c in range(max(lo[i],lo[j]),min(hi[i],hi[j])):
            ids=(i*b+c,i*b+c+1,j*b+c+1,j*b+c)
            if any(cv[k]<0 for k in ids):continue
            out.append(('road_proxy','road',[tuple(vv[3*k:3*k+3]) for k in ids],[(0,0),(1,0),(1,1),(0,1)]))
    _ROADF[:]=[signature,list(out)]
    return out
