"""NumPy-free DXT5 texture construction with explicit color adjustment."""
from array import array
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
    g=array('f',rgb.view());a=bytearray(0 if v else 255 for v in mask)
    d=bytearray(template.data[:172]);mips=[];hh,ww=h,w
    while True:
        H,W=max(4,hh),max(4,ww);pc=bytearray(H*W*3);pa=bytearray(H*W)
        for y in range(H):
            for x in range(W):
                src=min(y,hh-1)*ww+min(x,ww-1);dst=y*W+x
                pa[dst]=a[src]
                for k in range(3):pc[3*dst+k]=int(max(0.,min(255.,g[3*src+k])))
        col=fastdxt.dxt1_bytes(pc,H,W);blk=bytearray(len(col)*2)
        for by in range(H//4):
            for bx in range(W//4):
                block=by*(W//4)+bx;idx=0
                for iy in range(4):
                    for ix in range(4):
                        if pa[(by*4+iy)*W+bx*4+ix]<128:idx|=1<<(3*(iy*4+ix))
                p=16*block;blk[p]=255;blk[p+2:p+8]=idx.to_bytes(6,'little');blk[p+8:p+16]=col[8*block:8*block+8]
        mips.append(bytes(blk))
        if hh==ww==1:break
        # Vertical averaging precedes horizontal, with float32 rounding after
        # each axis; odd trailing rows/columns are discarded by the original.
        if hh>1:
            g=array('f',((g[(2*y*ww+x)*3+k]+g[((2*y+1)*ww+x)*3+k])/2 for y in range(hh//2) for x in range(ww) for k in range(3)))
            a=bytearray(min(a[2*y*ww+x],a[(2*y+1)*ww+x]) for y in range(hh//2) for x in range(ww));hh//=2
        if ww>1:
            g=array('f',((g[(y*ww+2*x)*3+k]+g[(y*ww+2*x+1)*3+k])/2 for y in range(hh) for x in range(ww//2) for k in range(3)))
            a=bytearray(min(a[y*ww+2*x],a[y*ww+2*x+1]) for y in range(hh) for x in range(ww//2));ww//=2
    struct.pack_into('<II',d,8,w,h)
    struct.pack_into('<III',d,56,h,w,len(mips[0]));struct.pack_into('<I',d,72,len(mips))
    return sbfw.Ch(4,new_id,bytes(d)+b''.join(mips),[],[])
