"""NumPy-free DXT5 texture construction with explicit color adjustment."""
from array import array
import ctypes
import struct
from npyio import Arr
from fastround import _buffer
import fastdxt
import sbfw


def _rgb(a):
    if not isinstance(a,Arr) or len(a.shape)!=3 or a.shape[2]!=3:
        raise ValueError('buildtexture: RGB must be u1(h,w,3) Arr')
    a=_buffer(a,'|u1',(a.shape[1],3),'rgb')
    h,w=a.shape[:2]
    if not h or not w or h*w>16777216:raise ValueError('buildtexture: invalid image size')
    hh,ww=h,w
    while True:
        if max(4,hh)%4 or max(4,ww)%4:raise ValueError('buildtexture: mip dimensions must fit DXT blocks')
        if hh==ww==1:break
        hh=max(1,hh//2);ww=max(1,ww//2)
    return a


def make_texture_dxt5(template,new_id,rgb,hole,adjust=None):
    """Return an sbfw.Ch with cloned header and the original binary-alpha mips.

    rgb: u1(h,w,3) Arr; hole: b1(h,w) Arr or None (opaque). Optional
    adjust(rgb) returns RGB of the same shape; use it for explicit vivid/gain
    policy. This function has no build_classic globals and imports no NumPy.
    The caller owns all input storage; outputs do not alias it.
    """
    rgb=_rgb(rgb);shape=rgb.shape;h,w=shape[:2]
    if len(template.data)<172:raise ValueError('buildtexture: short texture template')
    if hole is None:mask=bytes(h*w)
    else:
        hole=_buffer(hole,'|b1',(w,),'hole')
        if hole.shape!=(h,w):raise ValueError('buildtexture: mask shape mismatch')
        mask=bytes(hole.buf[:hole.nbytes])
    if adjust is not None:
        rgb=_rgb(adjust(rgb))
        if rgb.shape!=shape:raise ValueError('buildtexture: adjustment changed image shape')
    from geobuf import _native
    lib=_native();P=ctypes.c_void_p;I=ctypes.c_longlong
    lib.fg_texture_pad.argtypes=[P,P,I,I,P,P];lib.fg_texture_pad.restype=None
    lib.fg_texture_half.argtypes=[P,P,I,I,ctypes.c_int,P,P];lib.fg_texture_half.restype=None
    lib.fg_texture_alpha.argtypes=[P,I,I,P,P];lib.fg_texture_alpha.restype=None
    g=Arr('<f4',(h*w*3,),bytearray(array('f',rgb.view()).tobytes()))
    a=Arr('|u1',(h*w,),bytearray(0 if v else 255 for v in mask))
    d=bytearray(template.data[:172]);mips=[];hh,ww=h,w
    while True:
        H,W=max(4,hh),max(4,ww);pc=Arr('|u1',(H*W*3,));pa=Arr('|u1',(H*W,))
        lib.fg_texture_pad(g.ptr(),a.ptr(),hh,ww,pc.ptr(),pa.ptr())
        col=fastdxt.dxt1_bytes(pc.buf,H,W);color=ctypes.create_string_buffer(col,len(col));blk=Arr('|u1',(len(col)*2,))
        lib.fg_texture_alpha(pa.ptr(),H,W,color,blk.ptr());mips.append(bytes(blk.buf))
        if hh==ww==1:break
        # Vertical averaging precedes horizontal, with float32 rounding after
        # each axis; odd trailing rows/columns are discarded by the original.
        if hh>1:
            newg=Arr('<f4',(hh//2*ww*3,));newa=Arr('|u1',(hh//2*ww,))
            lib.fg_texture_half(g.ptr(),a.ptr(),hh,ww,1,newg.ptr(),newa.ptr());g,a=newg,newa;hh//=2
        if ww>1:
            newg=Arr('<f4',(hh*(ww//2)*3,));newa=Arr('|u1',(hh*(ww//2),))
            lib.fg_texture_half(g.ptr(),a.ptr(),hh,ww,0,newg.ptr(),newa.ptr());g,a=newg,newa;ww//=2
    struct.pack_into('<II',d,8,w,h)
    struct.pack_into('<III',d,56,h,w,len(mips[0]));struct.pack_into('<I',d,72,len(mips))
    return sbfw.Ch(4,new_id,bytes(d)+b''.join(mips),[],[])
