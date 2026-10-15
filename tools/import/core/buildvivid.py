"""Explicit NumPy-free color adjustment matching the importer's float32 steps."""
import ctypes
import functools
import math
import struct
from npyio import Arr
from fastround import _buffer

_fstruct=struct.Struct('<f')
def _f(x):return _fstruct.unpack(_fstruct.pack(x))[0]

@functools.lru_cache(maxsize=16)
def _curve(gamma):
    # NumPy 1.24's float32 power uses this Windows runtime function here.
    lib=ctypes.CDLL('ucrtbase');power=lib.powf
    power.argtypes=[ctypes.c_float,ctypes.c_float];power.restype=ctypes.c_float
    return tuple(_f(255.*power(_f(i/255.),gamma)) for i in range(256))

def _parameter(value,name):
    value=float(value)
    if not math.isfinite(value) or abs(value)>1e6:raise ValueError('buildvivid: unsupported '+name)
    return _f(value)

def vivid(rgb,config=None,scene_gain=None,no_gain=False):
    """u1(h,w,3) RGB -> RGB with explicit gain/saturation[/gamma] policy.

    Disabled config returns the same input, including ignoring scene_gain.
    Enabled output is owned/writable. Parameters must be finite and bounded
    by 1e6; gamma must be nonnegative. scene_gain is a scalar or three values.
    The source array and policy sequences are never mutated.
    """
    if not isinstance(rgb,Arr) or len(rgb.shape)!=3 or rgb.shape[2]!=3:
        raise ValueError('buildvivid: RGB must be u1(h,w,3) Arr')
    a=_buffer(rgb,'|u1',(rgb.shape[1],3),'rgb')
    if config is None or len(config)==0:return rgb
    if len(config) not in (2,3):raise ValueError('buildvivid: config requires two or three values')
    gain=_parameter(config[0],'gain');sat=_parameter(config[1],'saturation')
    curve=tuple(float(i) for i in range(256))
    if len(config)==3:
        gamma=_parameter(config[2],'gamma')
        if gamma<0:raise ValueError('buildvivid: negative gamma')
        curve=_curve(gamma)
    gains=None
    if scene_gain is not None and not no_gain:
        try:values=list(scene_gain)
        except TypeError:values=[scene_gain]*3
        if len(values)!=3:raise ValueError('buildvivid: scene gain requires scalar or three values')
        gains=[_parameter(v,'scene gain') for v in values]
    out=Arr('|u1',a.shape);dst=out.view();src=a.view()
    for i in range(0,a.size,3):
        x=[curve[src[i+k]] for k in range(3)]
        lum=_f(_f(_f(x[0]+x[1])+x[2])/3.)
        y=[max(_f(_f(lum+_f(_f(v-lum)*sat))*gain),0.) for v in x]
        top=max(y);scale=_f(255./max(top,1.)) if top>255. else 1.
        for k in range(3):
            v=_f(y[k]*scale)
            if gains is not None:v=_f(v*gains[k])
            dst[i+k]=int(max(0.,min(255.,v)))
    return out
