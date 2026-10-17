"""Disassemble the D3D9 shader bytecode inside an SR3 shader stub (kind 3 chunk): finds the vs_3_0 / ps_3_0 blobs
(version token 0xFFFE0300 / 0xFFFF0300 .. end token 0x0000FFFF) and runs D3DXDisassembleShader (d3dx9_43.dll, 64-bit,
from Windows' DirectX runtime) on them. Read-only.
    python shaderdis.py <file.sbf> <shader chunk id hex | material id hex> [out folder]
"""
import os, sys, struct, ctypes
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sbfw


def blobs(data):
    out = []
    for o in range(0, len(data) - 4, 4):
        v = struct.unpack_from("<I", data, o)[0]
        if v in (0xFFFE0300, 0xFFFF0300, 0xFFFE0200, 0xFFFF0200):
            e = o + 4
            while e + 4 <= len(data):
                t = struct.unpack_from("<I", data, e)[0]
                if t == 0x0000FFFF: out.append(("vs" if v >> 16 == 0xFFFE else "ps", data[o:e + 4])); break
                if (t & 0xFFFF) == 0xFFFE: e += 4 * ((t >> 16) & 0x7FFF)          # comment block (CTAB)
                e += 4
    return out


def disassemble(blob):
    d = ctypes.WinDLL("d3dx9_43.dll")
    class ID3DXBuffer(ctypes.Structure): pass
    p = ctypes.c_void_p()
    buf = ctypes.create_string_buffer(bytes(blob), len(blob))
    hr = d.D3DXDisassembleShader(buf, 0, None, ctypes.byref(p))
    if hr != 0: raise OSError("D3DXDisassembleShader 0x%08x" % (hr & 0xFFFFFFFF))
    vt = ctypes.cast(ctypes.cast(p, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
    GetPtr = ctypes.WINFUNCTYPE(ctypes.c_void_p, ctypes.c_void_p)(vt[3]); GetSize = ctypes.WINFUNCTYPE(ctypes.c_size_t, ctypes.c_void_p)(vt[4])
    Release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(vt[2])
    s = ctypes.string_at(GetPtr(p), GetSize(p)).rstrip(b"\0").decode("latin1"); Release(p)
    return s


def ctab(blob):
    """constant table (comment block 'CTAB') -> list of (name, register set, index, count); sets: 0 bool, 1 int, 2 float, 3 sampler"""
    o = 4
    while o + 4 <= len(blob):
        t = struct.unpack_from("<I", blob, o)[0]
        if (t & 0xFFFF) != 0xFFFE: break
        n = (t >> 16) & 0x7FFF
        body = blob[o + 4:o + 4 + 4 * n]
        if body[:4] == b"CTAB":
            c = body[4:]
            size, creator, ver, count, info, flags, target = struct.unpack_from("<7I", c, 0)
            out = []
            for k in range(count):
                nm, rs, ri, rc, _, ti, dv = struct.unpack_from("<I2H2H2I", c, info + 20 * k)
                out.append((c[nm:c.index(b"\0", nm)].decode(), ["bool", "int", "float", "sampler"][rs], ri, rc))
            return out
        o += 4 + 4 * n
    return []


if __name__ == "__main__":
    if sys.argv[1] == "--ctab":
        f = sbfw.read_sbf(sys.argv[2]); ids = f.byid(); c = ids[int(sys.argv[3], 16)]
        if c.kind == 2: c = ids[c.u32(0)]
        for k, (kind, b) in enumerate(blobs(c.data)):
            print("blob", k, kind, " ".join("%s=%s%d%s" % (nm, {"sampler": "s", "float": "c", "int": "i", "bool": "b"}[rs], ri, "(%d)" % rc if rc > 1 else "") for nm, rs, ri, rc in ctab(b)))
        sys.exit()
    f = sbfw.read_sbf(sys.argv[1]); ids = f.byid(); c = ids[int(sys.argv[2], 16)]
    if c.kind == 2: c = ids[c.u32(0)]
    out = sys.argv[3] if len(sys.argv) > 3 else None
    for k, (kind, b) in enumerate(blobs(c.data)):
        txt = disassemble(b)
        if out:
            os.makedirs(out, exist_ok=True)
            p = os.path.join(out, "%08x_%d_%s.txt" % (c.id, k, kind)); open(p, "w").write(txt); print("wrote", p, len(txt.splitlines()), "lines")
        else: print(txt)
