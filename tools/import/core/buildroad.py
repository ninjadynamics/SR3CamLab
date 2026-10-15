"""NumPy-free bilinear road heights on checked production f8 buffers."""
import math
from npyio import Arr
from fastround import _buffer
import buildnear
import fillroad


class RoadHeight:
    """Snapshot V/D/lat/hw and return f8(m) heights for f8(m,3) point Arrs.

    Uses the same nearest-slice ring search, lateral clamp, forward/backward
    slice selection and arithmetic order as fastbuild._road_height. Owns its
    native nearest index; close or use as a context manager.
    """
    def __init__(self,rd):
        self.near=None;hw,V,n,b=fillroad._inputs(rd)
        if hw<1 or n<1:raise ValueError('buildroad: road needs slices and positive half width')
        if V.dtype!='<f8':raise ValueError('buildroad: V must use f8')
        D=_buffer(rd['D'],'<f8',(3,),'D');lat=_buffer(rd['lat'],'<f8',(3,),'lat')
        if D.shape!=(n,3) or lat.shape!=(n,3):raise ValueError('buildroad: direction counts differ from slices')
        for a in (V,D,lat):
            if any(not math.isfinite(v) or abs(v)>1e50 for v in a.view()):raise ValueError('buildroad: nonfinite or oversized road value')
        self.V=Arr('<f8',V.shape,bytearray(V.buf));self.D=Arr('<f8',D.shape,bytearray(D.buf));self.lat=Arr('<f8',lat.shape,bytearray(lat.buf))
        self.hw=hw;self.n=n;self.b=b
        cen=Arr('<f8',(n,2));cv=cen.view();v=self.V.view()
        for k in range(n):cv[2*k]=v[3*(k*b+hw)];cv[2*k+1]=v[3*(k*b+hw)+2]
        self.cen=cen;self.near=buildnear.Near(cen)

    def __call__(self,points):
        if self.near is None:raise ValueError('buildroad: road is closed')
        points=_buffer(points,'<f8',(3,),'points');pv=points.view();m=points.shape[0];xz=Arr('<f8',(m,2));qv=xz.view()
        for k in range(m):qv[2*k]=pv[3*k];qv[2*k+1]=pv[3*k+2]
        indices=self.near(xz).view();out=Arr('<f8',(m,));ov=out.view();V=self.V.view();D=self.D.view();lat=self.lat.view();cen=self.cen.view();b=self.b;hw=self.hw;n=self.n
        for q,i in enumerate(indices):
            d0=pv[3*q]-cen[2*i];d1=pv[3*q+2]-cen[2*i+1]
            a=d0*D[3*i]+d1*D[3*i+2];c=(d0*lat[3*i]+d1*lat[3*i+2])+hw
            c=min(max(c,0.),2*hw-1e-6);k=int(c);fc=c-k;j=(i+(1 if a>=0 else -1))%n;fa=min(abs(a),1.)
            y0=V[3*(i*b+k)+1]*(1-fc)+V[3*(i*b+k+1)+1]*fc
            y1=V[3*(j*b+k)+1]*(1-fc)+V[3*(j*b+k+1)+1]*fc
            ov[q]=y0*(1-fa)+y1*fa
        return out

    def close(self):
        if self.near is not None:self.near.close();self.near=None

    def __enter__(self):
        if self.near is None:raise ValueError('buildroad: road is closed')
        return self

    def __exit__(self,*exc):self.close()

    def __del__(self):
        try:self.close()
        except Exception:pass
