"""Offline regression for SR3's dimension clamp / DDS mip mismatch."""
import struct
from texdxt import fit_texture_mips,texture_info

def chain(w,h,fc):
    b=bytearray(172);struct.pack_into('<II',b,8,w,h)
    struct.pack_into('<II',b,56,h,w);struct.pack_into('<I',b,72,max(w,h).bit_length());b[128:132]=fc.encode()
    payload=[];level=0;block=8 if fc=='DXT1' else 16
    while True:
        payload.append(bytes([level])*max(1,w//4)*max(1,h//4)*block)
        if w==h==1:break
        w=max(1,w//2);h=max(1,h//2);level+=1
    struct.pack_into('<I',b,64,len(payload[0]))
    return bytes(b)+b''.join(payload),payload

for fc in ('DXT1','DXT5'):
    for w,h in ((4096,4096),(4096,2048),(2048,2048),(512,512)):
        src,levels=chain(w,h,fc);out=fit_texture_mips(src)
        drop=1 if w>2048 else 0
        assert out[172:]==b''.join(levels[drop:])
        ow,oh,_=texture_info(out)
        assert (ow,oh)==(w>>drop,h>>drop)
        assert struct.unpack_from('<I',out,72)[0]==max(ow,oh).bit_length()
        assert fit_texture_mips(out)==out
        if not drop:assert out==src
        for broken in (src[:-1],src[:72]+struct.pack('<I',99)+src[76:]):
            try:fit_texture_mips(broken)
            except ValueError:pass
            else:raise AssertionError('Invalid mip chain accepted')
print('8 size/format cases plus malformed-chain rejection passed')
