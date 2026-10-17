"""SEGA Rally Championship colour data recovered statically.
- Palette (palram 0x1000 + colour base): the program copies its initialised data from ROM 0x1000.. to RAM 0x5A0000..
  at boot (loop at 0x528, RAM = ROM + 0x59F000; seen by running the reset code in i960.py). The palette source table the
  upload code reads at RAM 0x5FB89C (count, then 15-bit colours; code at 0x267B0 writes them to 0x1802000) is therefore
  program ROM 0x5C89C: 541 entries, one global table for all courses.
- Luma RAM: filled by the self-contained routine at 0x4590; executed here in the interpreter.
- colorxlat (0x1810000): copied by 0x330A0 from RAM tables at 0x210830.. that other code computes (brightness/fade
  dependent). NOT emulated: a linear ramp is assumed (output = colour * luma / 63), no gamma.
    python m2colour.py   -> ../tmp/m2/palette.npy (541 x 3 uint8), lumaram.npy (0x8000 uint8)
Without numpy since 2026-10-15 (kb 31): the tables are bytes, written by npyio (the same files np.save wrote). palette(), lumaram()
and colour_tile() still give the callers that compute with numpy (classic_tex, src_all, build_classic) numpy arrays, importing numpy
only then; palette_bytes() / lumaram_bytes() are the same tables for callers without numpy."""
import os, struct
import i960, npyio
PAL_ROM = 0x5c89c

def palette_bytes():
    """n x 3 bytes, r g b: each 5-bit channel * 255 // 31 (the numpy version: (np.stack([v & 31, ...], 1) * 255 // 31).astype(np.uint8))"""
    prog = open(os.path.join(i960.M2, 'maincpu.bin'), 'rb').read(); n = struct.unpack_from('<H', prog, PAL_ROM)[0]
    return bytes(((v >> s) & 31) * 255 // 31 for v in struct.unpack_from('<%dH' % n, prog, PAL_ROM + 2) for s in (0, 5, 10))

def palette():
    """(n, 3) uint8 numpy array, for the callers that compute with numpy"""
    import numpy as np
    return np.frombuffer(bytearray(palette_bytes()), np.uint8).reshape(-1, 3)

def lumaram_bytes():
    """0x8000 bytes: the luma RAM the routine at 0x4590 fills (computed once, then read from lumaram.npy)"""
    p = os.path.join(i960.M2, 'lumaram.npy')
    if os.path.exists(p): return bytes(npyio.load(p).buf)
    m = i960.Mem(); c = i960.Cpu(m); c.r[30] = 0xdead0000                 # g14 = return address for a bx (g14) exit
    res = c.run(0x4590, maxsteps=3000000, stop_at=(0xdead0000,))
    lr = bytearray(0x8000); n = 0
    for a, v in m.log.items():
        if 0x12800000 <= a < 0x12820000 and (a & 3) == 0: lr[(a - 0x12800000) >> 2] = v & 0xff; n += 1      # (numpy's uint8 store keeps the low byte too)
    print('luma routine: %s after %d steps, %d entries written, bases with data: %d' % (res, c.steps, n, len({i >> 7 for i in range(0x8000) if lr[i]})))
    npyio.save(p, npyio.Arr('|u1', (0x8000,), lr)); return bytes(lr)

def lumaram():
    """(0x8000,) uint8 numpy array, for the callers that compute with numpy"""
    import numpy as np
    return np.frombuffer(bytearray(lumaram_bytes()), np.uint8)

_XL = {}
def colour_tile(t, cb, lumabase, pal=None, lr=None, exact=True):
    """texel block (values 0..15) -> RGB uint8 the way the renderer combines them at full polygon brightness:
    luma = lumaram[base + texel * 8]; out[ch] = colorxlat[ch][5-bit palette channel][luma]   (table from m2xlat.py: the
    game's own fill routines executed; palette entries with r = g = b = odd pick one of ten gradient rows).
    exact=False: the old linear guess colour * luma / 63. (numpy in and out: its callers compute with numpy.)"""
    import numpy as np
    pal = palette() if pal is None else pal; lr = lumaram() if lr is None else lr
    l = np.minimum(lr[(lumabase << 7) + (t.astype(np.int32) << 3)].astype(np.int32), 63)
    c = pal[cb] if cb < len(pal) else np.array([128, 128, 128], np.uint8)
    if not exact: return np.clip((l / 63.0)[:, :, None] * c[None, None, :].astype(np.float32), 0, 255).astype(np.uint8)
    if 't' not in _XL:
        import m2xlat; _XL['t'] = m2xlat.table()
    c5 = (c.astype(np.int32) * 31 + 127) // 255; T = _XL['t']
    return np.stack([T[ch, c5[ch]][l] for ch in range(3)], 2).astype(np.uint8)

_XLB = {}
def colour_tables(cb, lumabase, pal, lr, alpha):
    """colour_tile (exact) as three bytes.translate tables: for each texel value 0..15 its red, green, blue byte (0 for texel 15 when
    alpha: to_image's hole), from palette_bytes() / lumaram_bytes(). The numpy lines: l = np.minimum(lr[(lumabase << 7) + (t << 3)], 63);
    c5 = (c * 31 + 127) // 255; out[ch] = colorxlat[ch, c5[ch]][l] - here per texel VALUE (16 of them) instead of per texel."""
    if 't' not in _XLB:
        import m2xlat; _XLB['t'] = m2xlat.table_bytes()
    T = _XLB['t']; c = pal[3 * cb:3 * cb + 3] if cb < len(pal) // 3 else bytes((128, 128, 128)); out = []
    for ch in range(3):
        c5 = (c[ch] * 31 + 127) // 255
        row = [T[(ch * 32 + c5) * 64 + min(lr[(lumabase << 7) + (v << 3)], 63)] for v in range(16)]
        if alpha: row[15] = 0
        out.append(bytes(row + [0] * 240))
    return out

if __name__ == '__main__':
    p = palette_bytes(); npyio.save(os.path.join(i960.M2, 'palette.npy'), npyio.Arr('|u1', (len(p) // 3, 3), bytearray(p))); print('palette entries', len(p) // 3)
    l = lumaram_bytes(); print('luma base 0 ramp (texel 0..15):', list(l[0:128:8]))
    for b in (1, 2, 3, 0x10, 0x40): print('luma base %02x:' % b, list(l[(b << 7):(b << 7) + 128:8]))
