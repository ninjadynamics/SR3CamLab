"""Offline regression for neutral compatibility and sunlight/sky colour separation."""
from pathlib import Path
import os, sys, ctypes, json
os.environ.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
C = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(C))
import numpy as np
import cbuild
from rtbake.lighting_tone import reference, apply_native, colors
cbuild.runtime()
L = ctypes.CDLL(cbuild.dll('rtcompose'))
Pv, Ii, LL, Dd = ctypes.c_void_p, ctypes.c_int, ctypes.c_longlong, ctypes.c_double
sig = [Pv, Ii, Ii] + [Pv]*6 + [LL, Dd, Dd, Pv, Pv, Pv]
L.rtc_pages.argtypes = sig
L.rtc_pages_toned.argtypes = sig + [Pv]*3

def compose(raw, tone=None, lib=L, road_flag=True):
    npg, side = raw.shape[:2]
    pg=np.array([1],np.int32);xy=np.array([0],np.int32);wh=np.array([side],np.int32);road=np.array([road_flag],np.uint8)
    out=np.zeros((npg,side,side,3),np.uint8);over=LL(0);lsum=Dd(0)
    args=[raw.ctypes.data,npg,side,pg.ctypes.data,xy.ctypes.data,xy.ctypes.data,wh.ctypes.data,wh.ctypes.data,road.ctypes.data,1,.34,.55,out.ctypes.data,ctypes.byref(over),ctypes.byref(lsum)]
    if tone:
        vec=[(ctypes.c_double*3)(*tone[k]) for k in ('sun','sky','reference')]
        lib.rtc_pages_toned(*args,*vec)
    else:lib.rtc_pages(*args)
    return out

rng=np.random.default_rng(70);raw=rng.integers(0,256,(2,64,64,7),dtype=np.uint8)
# Compare compiled legacy arithmetic to the retained pre-change library when available.
oldpath=C/'rtbake/rtcompose.28ab0637.x86-64-v3.dll'
if oldpath.exists():
    old=ctypes.CDLL(str(oldpath));old.rtc_pages.argtypes=sig
    assert np.array_equal(compose(raw),compose(raw,lib=old))
neutral=compose(raw)
assert neutral.shape==(2,64,64,3)
# A deliberately achromatic road still receives warm sunlight and cool skylight.
raw=np.zeros((1,4,4,7),np.uint8);raw[...,1]=255;raw[...,5]=180;raw[...,6]=255
raw[:,:,:2,0]=255
warm=dict(sun=[1.08,.78,.72],sky=[.88,.92,1.02],reference=[1,1,1])
out=compose(raw,warm);sun=out[0,0,0].astype(float);shade=out[0,0,3].astype(float)
assert sun[0]>1.1*max(sun[1],sun[2]),sun
assert shade[2]>shade[1]>shade[0],shade
# Dividing by native ground colour prevents applying the warmth twice.
ref=[1.04,.83,.84];comp=compose(raw,dict(warm,reference=ref)).astype(float)*ref
assert np.max(np.abs(comp-out))<=1.1
fl=np.array([0,0,-1,0,.58,.627,.71,1.2,1.05,1]+[0]*13+[1.1,1.05,1]+[0]*23,float)
r=reference(fl,[0,-1,0],.72,warm)
assert all(.7<v<1.1 for v in r)
a=fl.copy();apply_native(a,warm)
assert np.array_equal(a[:4],fl[:4]) and np.array_equal(a[10:],fl[10:])
assert np.allclose(a[4:7],fl[4:7]*warm['sky']) and np.allclose(a[7:10],fl[7:10]*warm['sun'])
for bad in [[1,2], [1,float('nan'),1], [1,-.1,1]]:
    try:colors(dict(sun=bad))
    except ValueError:pass
    else:raise AssertionError('invalid colour accepted')
print(json.dumps(dict(status='PASS',neutral_legacy_bytes_identical=oldpath.exists(),sun_rgb=sun.tolist(),shadow_rgb=shade.tolist(),double_tint_compensation=True,native_geometry_and_direction_untouched=True)))
