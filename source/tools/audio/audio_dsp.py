"""Small interleaved PCM buffers and the audio C helper; no numerical package."""
import ctypes as C
import math
import os
import sys
from functools import lru_cache

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'import', 'core'))
import cbuild

_lib = None

def lib():
    global _lib
    if _lib is None:
        cbuild.runtime(); _lib = C.CDLL(cbuild.dll('audio_dsp'))
        P, N, I, D = C.c_void_p, C.c_size_t, C.c_int, C.c_double
        for name, ret, args in (
            ('sum', D, [P,N,I]), ('pcm', None, [P,P,N,I]),
            ('scale', None, [P,P,N,D,I]), ('peak', D, [P,N]),
            ('column', None, [P,P,N,I,I]), ('wav', None, [P,P,N]),
            ('ramp', None, [P,N,I,I]), ('blend', None, [P,P,N,I]),
            ('envelope', None, [P,P,N,N]), ('percentile', D, [P,N,D]),
            ('crossing', N, [P,N,I,D,I]), ('frame_peak', None, [P,P,N,I]),
            ('diff', None, [P,P,N,I]), ('loud', D, [P,N,N]),
            ('short', None, [P,N,I,P,N,P,I,I,I]),
            ('long', I, [P,N,I,P,N,N,N,D]), ('corr', D, [P,P,N]),
            ('voice_score', D, [P,N,P,N])):
            f=getattr(_lib, 'ad_'+name); f.restype=ret; f.argtypes=args
    return _lib

class PCM:
    """Contiguous doubles, frame slices are views; copy only when modifying."""
    def __init__(self, frames, channels=1, owner=None, offset=0):
        if frames<0 or channels<1 or offset<0:raise ValueError('Invalid PCM shape')
        self.frames=frames; self.channels=channels
        self.owner=owner if owner is not None else (C.c_double*(frames*channels))()
        if offset+frames*channels>len(self.owner):raise ValueError('PCM view exceeds storage')
        self.offset=offset
    @property
    def ptr(self): return C.addressof(self.owner)+self.offset*8
    @property
    def size(self): return self.frames*self.channels
    def __len__(self): return self.frames
    def __getitem__(self, key):
        if isinstance(key, tuple):
            rows,col=key; return self[rows].column(col)
        if isinstance(key, int):
            if key<0:key+=self.frames
            if not 0<=key<self.frames:raise IndexError(key)
            return self.owner[self.offset+key] if self.channels==1 else tuple(self.owner[self.offset+key*self.channels+j] for j in range(self.channels))
        a,b,step=key.indices(self.frames)
        if step!=1:raise ValueError('PCM frame slices need step 1')
        return PCM(max(0,b-a),self.channels,self.owner,self.offset+a*self.channels)
    def copy(self):
        y=PCM(len(self),self.channels); C.memmove(y.ptr,self.ptr,self.size*8);return y
    def column(self, col):
        if not -1<=col<self.channels:raise ValueError('Invalid PCM channel')
        y=PCM(len(self));lib().ad_column(self.ptr,y.ptr,len(self),self.channels,col);return y
    def tobytes(self):return C.string_at(self.ptr,self.size*8)

def from_pcm(raw, bits=16, channels=1):
    if bits not in (8,16) or channels<1 or len(raw)%(bits//8):raise ValueError('Invalid PCM format')
    n=len(raw)//(bits//8)
    if n%channels:raise ValueError('Incomplete PCM frame')
    y=PCM(n//channels,channels);lib().ad_pcm(raw,y.ptr,n,bits);return y
def from_values(values):
    vals=list(values); y=PCM(len(vals));y.owner[:]=vals;return y
def concat(parts):
    ch=parts[0].channels if parts else 1
    if any(p.channels!=ch for p in parts):raise ValueError('Different PCM channel counts')
    y=PCM(sum(map(len,parts)),ch);offset=0
    for p in parts:C.memmove(y.ptr+offset*8,p.ptr,p.size*8);offset+=p.size
    return y
def peak(x):return lib().ad_peak(x.ptr,x.size)
def sumsq(x):return lib().ad_sum(x.ptr,x.size,1)
def rms(x):return math.sqrt(sumsq(x)/x.size) if x.size else 0.
def scale(x,g,limit=False):
    y=PCM(len(x),x.channels);lib().ad_scale(x.ptr,y.ptr,x.size,g,limit);return y
def ramp(x,reverse=False):lib().ad_ramp(x.ptr,len(x),x.channels,reverse)
def blend(x,b):
    if len(x)!=len(b) or x.channels!=b.channels:raise ValueError('Blend shape mismatch')
    lib().ad_blend(x.ptr,b.ptr,len(x),x.channels)
def envelope(x,hop):
    y=PCM(len(x)//hop);lib().ad_envelope(x.ptr,y.ptr,len(y),hop*x.channels);return y
def loud(x,rate,frame):
    if int(frame*rate)<1:raise ValueError('RMS frame must contain samples')
    value=lib().ad_loud(x.ptr,x.size,int(frame*rate)*x.channels)
    if not math.isfinite(value):raise ValueError('Empty audio or unavailable RMS workspace')
    return value
def percentile(x,q):
    y=x.copy();return lib().ad_percentile(y.ptr,y.size,q/100.)
def crossing(x,threshold,last=False):return lib().ad_crossing(x.ptr,len(x),x.channels,threshold,last)
def onset(x,lead=64):
    e=PCM(len(x));lib().ad_frame_peak(x.ptr,e.ptr,len(x),x.channels)
    i=crossing(e,max(.02*percentile(e,99.5),8.));return max(0,i-lead) if i<len(x) else 0
def seam(x,start):
    a=x[-1];b=x[start];step=max(abs(p-q) for p,q in zip(a,b))
    part=x[max(0,start-3200):start+3200];d=PCM(max(0,len(part)-1),x.channels)
    lib().ad_diff(part.ptr,d.ptr,len(d),x.channels)
    return step,percentile(d,95)+1.
def wav_bytes(x):
    y=(C.c_int16*x.size)();lib().ad_wav(x.ptr,y,x.size);return bytes(y)
def correlation(a,b):return lib().ad_corr(a.ptr,b.ptr,min(len(a),len(b)))
def voice_score(x,ref):
    if x.channels!=1 or ref.channels!=1 or not 0<len(ref)<len(x):raise ValueError('Voice comparison needs mono clips of different lengths')
    value=lib().ad_voice_score(x.ptr,len(x),ref.ptr,len(ref))
    if not math.isfinite(value):raise MemoryError('Voice comparison FFT failed')
    return value

def _i0(x):
    # This can actually be done with numpy the following way: np.i0(x);
    # it's done this way because the cached short FIR only needs scalar values.
    # Cephes coefficients and recurrence used by NumPy 1.24 (AUDIO-LICENSE.txt).
    a=(-4.4153416464793395e-18,3.3307945188222384e-17,-2.431279846547955e-16,1.715391285555133e-15,-1.1685332877993451e-14,7.676185498604936e-14,-4.856446783111929e-13,2.95505266312964e-12,-1.726826291441556e-11,9.675809035373237e-11,-5.189795601635263e-10,2.6598237246823866e-9,-1.300025009986248e-8,6.046995022541919e-8,-2.670793853940612e-7,1.1173875391201037e-6,-4.4167383584587505e-6,1.6448448070728896e-5,-5.754195010082104e-5,.00018850288509584165,-.0005763755745385824,.0016394756169413357,-.004324309995050576,.010546460394594998,-.02373741480589947,.04930528423967071,-.09490109704804764,.17162090152220877,-.3046826723431984,.6767952744094761)
    b=(-7.233180487874754e-18,-4.830504485944182e-18,4.46562142029676e-17,3.461222867697461e-17,-2.8276239805165836e-16,-3.425485619677219e-16,1.7725601330565263e-15,3.8116806693526224e-15,-9.554846698828307e-15,-4.150569347287222e-14,1.54008621752141e-14,3.8527783827421426e-13,7.180124451383666e-13,-1.7941785315068062e-12,-1.3215811840447713e-11,-3.1499165279632416e-11,1.1889147107846439e-11,4.94060238822497e-10,3.3962320257083865e-9,2.266668990498178e-8,2.0489185894690638e-7,2.8913705208347567e-6,6.889758346916825e-5,.0033691164782556943,.8044904110141088)
    z=x/2.-2. if x<=8 else 32./x-2.;coeff=a if x<=8 else b;b0=coeff[0];b1=0.
    for c in coeff[1:]:b2=b1;b1=b0;b0=z*b1-b2+c
    val=math.exp(x)*(.5*(b0-b2));return val if x<=8 else val/math.sqrt(x)

@lru_cache(maxsize=16)
def _kernel(L,M,taps,att):
    beta=.1102*(att-8.7) if att>50 else .5842*(att-21)**.4+.07886*(att-21)
    width=(att-7.95)/(2.285*2*math.pi*taps);fc=min(.5,.5*L/M)-width/2
    total=taps*L;alpha=total/2;den=_i0(beta);h=PCM(total)
    for r in range(L):
        for j in range(taps):
            k=j*L+r;n=k-total//2;arg=2*fc*n/L;v=math.pi*(arg if arg else 1e-20)
            window=_i0(beta*math.sqrt(1.-((k-alpha)/alpha)**2))/den
            h.owner[r*taps+j]=(2*fc*(math.sin(v)/v))*window
        ptr=h.ptr+r*taps*8;s=lib().ad_sum(ptr,taps,0)
        for j in range(taps):h.owner[r*taps+j]/=s
    return h

def resample_long(x,src,dst,edge=.93):
    if int(src)<1 or int(dst)<1 or not 0<=edge<1:raise ValueError('Invalid resampling rate or edge')
    g=math.gcd(int(src),int(dst));L=int(dst)//g;M=int(src)//g;k=1
    while M*k<len(x)+4096:k*=2
    y=PCM(round(len(x)*L/M),x.channels)
    if lib().ad_long(x.ptr,len(x),x.channels,y.ptr,len(y),M*k,L*k,edge):raise MemoryError('Audio FFT failed')
    return y
def resample(x,src,dst,taps=64,att=80.):
    if int(src)<1 or int(dst)<1 or taps<2 or att<21:raise ValueError('Invalid resampling rate or filter')
    if src==dst:return x.copy()
    if len(x)*taps*dst/src>8_000_000:return resample_long(x,src,dst)
    g=math.gcd(int(src),int(dst));L=int(dst)//g;M=int(src)//g;h=_kernel(L,M,taps,att)
    y=PCM(round(len(x)*L/M),x.channels)
    lib().ad_short(x.ptr,len(x),x.channels,y.ptr,len(y),h.ptr,L,M,taps);return y
