"""NumPy-free leaf/stem row sampling for fill1995, on checked image buffers."""
import math
import operator
import sys
from npyio import Arr
from fastround import _buffer


def image_buffer(im,alpha=False):
    """Borrow contiguous bool/RGBA images; copy strided buffer-protocol inputs."""
    if isinstance(im,Arr):return im
    m=memoryview(im)
    if m.format!=('?' if alpha else 'B'):raise ValueError('filltex: expected bool or uint8 image')
    return Arr('|b1' if alpha else '|u1',m.shape,m.cast('B') if m.c_contiguous else m.tobytes())


def _image(im,alpha):
    rank=2 if alpha else 3;dtype='|b1' if alpha else '|u1'
    if not isinstance(im,Arr) or len(im.shape)!=rank or (not alpha and im.shape[-1]!=4):
        raise ValueError('filltex: expected alpha(h,w) or RGBA(h,w,4) Arr')
    im=_buffer(im,dtype,im.shape[1:],'image')
    if im.shape[0]<1 or im.shape[1]<1:raise ValueError('filltex: empty image')
    return im


def _columns(width,u0,u1):
    # Preserve the input scalar's subtraction/rounding for the sample count.
    # linspace itself promotes endpoints to float64, including float32 inputs.
    m=max(int(round(abs(u1-u0)*width)),2)
    if m>sys.maxsize:raise ValueError('filltex: sample count too large')
    start=float(u0);delta=float(u1)-start
    if not math.isfinite(start) or not math.isfinite(delta):raise ValueError('filltex: nonfinite UV range')
    step=delta/m
    for i in range(m):
        # NumPy linspace avoids losing subnormal delta when step underflows.
        u=((i/m)*delta if step==0. else i*step)+start
        scaled=u*width
        x=math.floor(scaled) if math.isfinite(scaled) else -(1<<31)
        # The legacy .astype(int) is int32 on Windows. Keep its overflow
        # sentinel before modulo, including large but finite repeated UVs.
        if x<-(1<<31) or x>=(1<<31):x=-(1<<31)
        yield x%width


def stem_runs(alpha,row,u0,u1):
    """Same opaque fraction and number of opaque runs as fill1995._stem_runs."""
    im=_image(alpha,True);h,w=im.shape
    row=operator.index(row)
    if not -h<=row<h:raise ValueError('filltex: invalid row')
    offset=(row%h)*w;v=im.view();count=opaque=runs=0;previous=False
    for col in _columns(w,u0,u1):
        current=bool(v[offset+col]);count+=1;opaque+=current
        runs+=current and not previous;previous=current
    return opaque/count,runs


def leaf_row(rgba,v,u0,u1):
    """Whether the opaque sampled texels have mean green > 1.08*mean red."""
    im=_image(rgba,False);h,w,_=im.shape
    row=math.floor((1.-float(v))*h)%h;pixels=im.view();offset=row*w*4
    count=red=green=0
    for col in _columns(w,u0,u1):
        k=offset+4*col
        if pixels[k+3]>127:
            count+=1;red+=pixels[k];green+=pixels[k+1]
    return bool(count) and green/count>1.08*(red/count)
