"""Additive packed mesh operations; meshgen's ndarray API remains unchanged.

Vertices are owned '|V48' (4*n,) Arrs containing meshgen.VTX's exact layout:
position f4[4], normal f4[3], tangent f4[3], uv0 u2[2], uv1 u2[2].
This module imports no NumPy and does not install or replace legacy functions.
"""
import ctypes
import struct
import sys

from npyio import Arr
from fastround import _buffer


def parse_mesh(c):
    """Mesh metadata plus borrowed read-only |V48 vertices / <u2 indices.

    Only stride-48 meshes expose vertices, as in meshgen. The chunk's bytes
    stay alive through the returned memoryviews. Malformed ranges fail early.
    """
    d = memoryview(c.data).cast('B')
    def span(offset, size):
        if offset < 0 or size < 0 or offset > len(d) or size > len(d)-offset:
            raise ValueError('meshbuf: truncated mesh range')
        return d[offset:offset+size].toreadonly()
    h = struct.unpack('<18I', span(0,72))
    m = dict(stride=h[0], fmt=h[2], nv=h[5], ni=h[7], ng=h[8], pg=h[11], pv=h[12], pi=h[13], hdr=h)
    m['groups'] = list(struct.iter_unpack('<5I', span(m['pg'],20*m['ng'])))
    if m['stride'] == 48: m['verts'] = Arr('|V48',(m['nv'],),span(m['pv'],48*m['nv']))
    m['idx'] = Arr('<u2',(m['ni'],),span(m['pi'],2*m['ni']))
    e = m['pi']+2*m['ni']; m['rest'] = e+(-e%4)
    if not c.fix: raise ValueError('meshbuf: missing mesh tail fixup')
    m['tail'] = max(c.fix)
    span(m['rest'],0); span(m['tail'],4)
    return m


def _lib():
    from geobuf import _native
    L = _native(); P = ctypes.c_void_p; I = ctypes.c_longlong
    L.fg_mesh_bounds.argtypes = [P,I,P]; L.fg_mesh_bounds.restype = None
    L.fg_mesh_winding.argtypes = [P,I,P,I,P]; L.fg_mesh_winding.restype = ctypes.c_int
    return L


def winding_sign(c):
    """Same strip parity, degenerate-index skipping and (sign, score) result."""
    m = parse_mesh(c)
    if 'verts' not in m: raise ValueError('meshbuf: winding requires stride 48')
    v = _buffer(m['verts'],'|V48',(),'vertices')
    idx = _buffer(m['idx'],'<u2',(),'indices'); score = ctypes.c_longlong()
    if _lib().fg_mesh_winding(v.ptr(),v.size,idx.ptr(),idx.size,ctypes.byref(score)):
        raise ValueError('meshbuf: vertex index out of range')
    return (1 if score.value >= 0 else -1),score.value


def clone_mesh(tpl,new_id,verts,strip,material_id,name=None):
    """Clone a single-group mesh using |V48 vertices and <u2 strip Arrs.

    Inputs are borrowed. Returns an independent sbfw.Ch, preserving the legacy
    header, padding, fixup/reference relocation and in-place name truncation.
    """
    import sbfw
    m = parse_mesh(tpl); d = tpl.data
    if not (m['ng']==1 and m['stride']==48 and m['pg']==0x48 and m['pv']==0x5c):
        raise ValueError('meshbuf: clone requires a single-group stride-48 template')
    verts = _buffer(verts,'|V48',(),'vertices'); strip = _buffer(strip,'<u2',(),'indices')
    nv,ni = verts.size,strip.size
    if not (0<nv<65536 and 0<ni<65536): raise ValueError('meshbuf: nonempty u16 mesh limits exceeded')
    g = list(m['groups'][0]); g[1]=nv; g[2]=0; g[3]=(g[3]&0xffff0000)|ni; g[4]=material_id
    vb = bytes(verts.buf); ib = bytes(strip.buf); ib += b'\0'*(-len(ib)%4)
    pv=0x5c; pi=pv+len(vb); rest_old=m['rest']; delta=pi+len(ib)-rest_old
    h=list(m['hdr']); h[5]=nv; h[7]=ni; h[11]=0x48; h[12]=pv; h[13]=pi
    rest=bytearray(d[rest_old:]); fix=[0x2c,0x30,0x34]
    for o in tpl.fix:
        if o<rest_old: continue
        if o>len(d)-4: raise ValueError('meshbuf: fixup outside template')
        v=struct.unpack_from('<I',rest,o-rest_old)[0]
        if v>=rest_old: struct.pack_into('<I',rest,o-rest_old,v+delta)
        fix.append(o+delta)
    t=m['tail']-rest_old
    if t<0 or t+0x34>len(rest): raise ValueError('meshbuf: missing bounds in template tail')
    bounds=Arr('<f4',(9,)); _lib().fg_mesh_bounds(verts.ptr(),nv,bounds.ptr())
    # Match the original f4 -> Python float -> struct pack conversion, including
    # quieting signaling NaN payloads when serializing the nine bounds values.
    rest[t+0x10:t+0x34]=struct.pack('<9f',*bounds.view())
    if name is not None:
        for o in tpl.fix:
            if o<rest_old: continue
            v=struct.unpack_from('<I',d,o)[0]
            if v>=rest_old:
                if v>=len(d): raise ValueError('meshbuf: string pointer outside template')
                if (0x20<=d[v]<0x7f and d[v:v+4].isalnum()) or d[v:v+4]==b'sta_':
                    e=d.index(b'\0',v); size=e-v; nb=name.encode()[:size]
                    rest[v-rest_old:v-rest_old+size]=nb+b'\0'*(size-len(nb))
    data=struct.pack('<18I',*h)+struct.pack('<5I',*g)+vb+ib+bytes(rest)
    ref=[0x58]+[o+delta for o in tpl.ref if o>=rest_old]
    return sbfw.Ch(1,new_id,data,sorted(fix),ref)


def make_verts_safe(Q):
    """Checked '<f8' (n,4,3) corners -> owned '|V48' (4*n,) records.

    Corner 2 defines the normal, including triangle quads with repeated corners.
    Norms <= 1e-9 (or NaN) use the legacy normal/tangent fallback. Input storage
    is borrowed, never modified; read-only and unaligned buffers are accepted.
    """
    Q = _buffer(Q, '<f8', (4,3), 'quad corners')
    n = Q.shape[0]
    if n > sys.maxsize // 192: raise ValueError('meshbuf: vertex output too large')
    out = Arr('|V48', (4*n,))
    # NumPy's cross/norm/repeat plus structured-field assignment, performed in
    # one C pass to preserve the record bytes without intermediate arrays.
    if n:
        from geobuf import _native
        L = _native()
        L.fg_mesh_verts_safe.argtypes = [ctypes.c_void_p, ctypes.c_longlong, ctypes.c_void_p]
        L.fg_mesh_verts_safe.restype = None
        L.fg_mesh_verts_safe(Q.ptr(), n, out.ptr())
    return out
