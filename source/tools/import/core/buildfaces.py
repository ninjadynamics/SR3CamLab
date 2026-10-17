"""Packed face assembly with explicit flat/design-sun lighting policy.

Baked-light tables, lightmap collection/lookup and bump relief are separate
policies and are not applied here. Legacy callers must retain those branches.
"""
import math
import struct
from npyio import Arr
import buildmesh
import buildsmooth
import meshbuf
from npexact import ddot

def _dot(a,b):return (a[0]*b[0]+a[1]*b[1])+a[2]*b[2]
def _length(a):return math.sqrt(_dot(a,a))
def _f(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def _clip(x,a,b):return max(a,min(b,x))

def faces_to_mesh(faces,uv_mode,up_normals=False,light_k=0.,
                  light_env=(.64,1.08,(0.,.94,-.34)),smooth=None,
                  flat_lit=(),lm_cutouts=(),lm_test=False):
    """Return (owned |V48 Arr, quad count, clamped-face count).

    Handles original/flat/design-sun normals, smooth overrides, uncertain-side
    materials, cutout/sign exceptions and diagnostic lightmap UVs. smooth is
    a buildsmooth.Smooth snapshot or None. No implicit global state is changed.
    """
    prepared=buildmesh.mesh_uv(faces,uv_mode)
    if prepared is None:raise ValueError('buildfaces: unsupported face layout')
    q,uv,clamp=prepared;v=meshbuf.make_verts_safe(q);nv=len(faces)*4
    if up_normals and light_k>0:
        if not math.isfinite(light_k):raise ValueError('buildfaces: invalid contrast')
        normals=Arr('<f8',(nv,3));positions=Arr('<f4',(nv,4));nn=normals.view();pp=positions.view()
        for i in range(nv):
            for k,x in enumerate(struct.unpack_from('<4f',v.buf,48*i)):pp[4*i+k]=x
            for k,x in enumerate(struct.unpack_from('<3f',v.buf,48*i+16)):nn[3*i+k]=x
        if smooth is not None:normals=smooth.apply(normals,positions);nn=normals.view()
        amb,sun,sv=light_env;sv=tuple(map(float,sv));ln=math.sqrt(ddot(sv,sv))
        if not ln or not all(math.isfinite(x) for x in (amb,sun,*sv)):raise ValueError('buildfaces: invalid light environment')
        sv=tuple(x/ln for x in sv);sh=(sv[0],0.,sv[2]);lh=math.sqrt(ddot(sh,sh))
        sd=tuple(sh[k]/lh*.7071+(0.,.7071,0.)[k] for k in range(3)) if lh>1e-6 else (0.,1.,0.)
        floor=1.-.6*light_k;ground=amb+sun*max(sv[1],0.)
        alt=(0.,sv[2],-sv[1]);al=math.sqrt(ddot(alt,alt))
        if not al:raise ValueError('buildfaces: sun parallel to fallback axis')
        alt=tuple(x/al for x in alt)
        def bright(n):return floor+(1.-floor)*_clip((_dot(n,sd)+.2)/.907,0.,1.)
        for i in range(nv):
            n=tuple(nn[3*i:3*i+3]);name=str(faces[i//4][0]);base=name.split('|')[0]
            intensity=bright(n)
            if name.endswith('|4'):intensity=max(intensity,bright(tuple(-x for x in n)))
            if (base.endswith('_t') and base not in lm_cutouts) or base in flat_lit:intensity=1.
            cosine=_clip((intensity*ground-amb)/max(sun,1e-6),-1.,1.)
            dot=_dot(n,sv);e=tuple(n[k]-dot*sv[k] for k in range(3));length=_length(e)
            e=tuple(x/max(length,1e-9) for x in e) if length>1e-6 else alt
            scale=math.sqrt(1.-cosine*cosine)
            struct.pack_into('<3f',v.buf,48*i+16,*(cosine*sv[k]+scale*e[k] for k in range(3)))
    elif up_normals:
        for i in range(nv):struct.pack_into('<3f',v.buf,48*i+16,0.,1.,0.)
    if lm_test:
        for face in range(len(faces)):
            centres=[]
            for axis in (0,2):
                values=[struct.unpack_from('<f',v.buf,48*(4*face+j)+4*axis)[0] for j in range(4)]
                centres.append(_f(_f(_f(_f(values[0]+values[1])+values[2])+values[3])/4.))
            key=(math.floor(_f(centres[0]/16.))+2*math.floor(_f(centres[1]/16.)))%4
            for j in range(4):struct.pack_into('<2H',v.buf,48*(4*face+j)+44,8192 if key%2==0 else 24576,8192 if key<2 else 24576)
    packed=buildmesh.pack_uv(uv)
    for i in range(nv):v.buf[48*i+40:48*i+44]=packed.buf[4*i:4*i+4]
    return v,len(faces),clamp
