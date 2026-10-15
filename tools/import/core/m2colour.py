"""SEGA Rally Championship colour data recovered statically.
- Palette (palram 0x1000 + colour base): the program copies its initialised data from ROM 0x1000.. to RAM 0x5A0000..
  at boot (loop at 0x528, RAM = ROM + 0x59F000; seen by running the reset code in i960.py). The palette source table the
  upload code reads at RAM 0x5FB89C (count, then 15-bit colours; code at 0x267B0 writes them to 0x1802000) is therefore
  program ROM 0x5C89C: 541 entries, one global table for all courses.
- Luma RAM: filled by the self-contained routine at 0x4590; executed here in the interpreter.
- colorxlat (0x1810000): copied by 0x330A0 from RAM tables at 0x210830.. that other code computes (brightness/fade
  dependent). NOT emulated: a linear ramp is assumed (output = colour * luma / 63), no gamma.
    python m2colour.py   -> ../tmp/m2/palette.npy (541 x 3 uint8), lumaram.npy (0x8000 uint8)"""
import os, struct, numpy as np
import i960
PAL_ROM = 0x5c89c

def palette():
    prog = open(os.path.join(i960.M2, 'maincpu.bin'), 'rb').read(); n = struct.unpack_from('<H', prog, PAL_ROM)[0]
    v = np.array(struct.unpack_from('<%dH' % n, prog, PAL_ROM + 2), np.int32)
    c5 = np.stack([v & 31, (v >> 5) & 31, (v >> 10) & 31], 1)
    return (c5 * 255 // 31).astype(np.uint8)

def lumaram():
    p = os.path.join(i960.M2, 'lumaram.npy')
    if os.path.exists(p): return np.load(p)
    m = i960.Mem(); c = i960.Cpu(m); c.r[30] = 0xdead0000                 # g14 = return address for a bx (g14) exit
    res = c.run(0x4590, maxsteps=3000000, stop_at=(0xdead0000,))
    lr = np.zeros(0x8000, np.uint8); n = 0
    for a, v in m.log.items():
        if 0x12800000 <= a < 0x12820000 and (a & 3) == 0: lr[(a - 0x12800000) >> 2] = v; n += 1
    print('luma routine: %s after %d steps, %d entries written, bases with data: %d' % (res, c.steps, n, len({i >> 7 for i in range(0x8000) if lr[i]})))
    np.save(p, lr); return lr

_XL = {}
def colour_tile(t, cb, lumabase, pal=None, lr=None, exact=True):
    """texel block (values 0..15) -> RGB uint8 the way the renderer combines them at full polygon brightness:
    luma = lumaram[base + texel * 8]; out[ch] = colorxlat[ch][5-bit palette channel][luma]   (table from m2xlat.py: the
    game's own fill routines executed; palette entries with r = g = b = odd pick one of ten gradient rows).
    exact=False: the old linear guess colour * luma / 63."""
    pal = palette() if pal is None else pal; lr = lumaram() if lr is None else lr
    l = np.minimum(lr[(lumabase << 7) + (t.astype(np.int32) << 3)].astype(np.int32), 63)
    c = pal[cb] if cb < len(pal) else np.array([128, 128, 128], np.uint8)
    if not exact: return np.clip((l / 63.0)[:, :, None] * c[None, None, :].astype(np.float32), 0, 255).astype(np.uint8)
    if 't' not in _XL:
        import m2xlat; _XL['t'] = m2xlat.table()
    c5 = (c.astype(np.int32) * 31 + 127) // 255; T = _XL['t']
    return np.stack([T[ch, c5[ch]][l] for ch in range(3)], 2).astype(np.uint8)

if __name__ == '__main__':
    p = palette(); np.save(os.path.join(i960.M2, 'palette.npy'), p); print('palette entries', len(p))
    l = lumaram(); print('luma base 0 ramp (texel 0..15):', l[0:128:8].tolist())
    for b in (1, 2, 3, 0x10, 0x40): print('luma base %02x:' % b, l[(b << 7):(b << 7) + 128:8].tolist())
