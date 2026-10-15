"""Walk the authored minimal object / camera data the way the loader code does (static check; nothing is run in the game).
    python check_min.py [step folder] [slot]
game_objects (0x5BF450, 0x5BBFF0, 0x5BCC40, 0x5C04B0, 0x5BE010):
  root != 0 ; [root] >= 3 else the shape table pointer is taken as 0 and dereferenced ; table = [root+0x10], count [table]
  objects n = [root+4], records [root+8] + 0x54 * i ; descriptor [root+0xC] = {?, count +4, ptr +8 (0x2C each)}
  0x5C5E27: if [root] >= 2 the gameobj_dis file is looked up; missing -> 0 -> 0x5BE010 returns 0 (test at 0x5BE01D)
cameras (0x5FB250): [master_xdata root + 0xC] == 0 -> return ; else lists at +8 (intro), +4 (trackside), +0xC (postrace);
  list (0x5FB180): pointer 0 -> skipped ; [list] must be 0 ; count [list+4] ; kinds 0, 1, 2 only."""
import os, sys, struct
from common import *
import sbfw

def main(step='step22_classic_no_cameras_desert4', slot='Desert4'):
    d = os.path.join(OUT, step, slot); tf = track_files(d); ok = True
    def say(c, t):
        nonlocal ok; ok &= bool(c); print('   %s %s' % ('ok  ' if c else 'FAIL', t))
    print(step, sorted(os.listdir(d)))
    g = sbfw.read_sbf(tf['game_objects_gfx_data']); r = g.chunks[-1]; D = r.data
    def ptr(o):
        assert o in r.fix, 'offset %x is not a pointer fixup' % o; v = r.u32(o); assert v + 4 <= len(D); return v
    say(len(g.chunks) == 1 and r.kind == 5, 'one kind 5 chunk, %d bytes, %d pointers, %d references' % (len(D), len(r.fix), len(r.ref)))
    say(r.u32(0) >= 3, 'version %d >= 3' % r.u32(0)); n = r.u32(4); objs = ptr(8); say(objs + 0x54 * n <= len(D), '%d objects, records at +%x inside the chunk' % (n, objs))
    de = ptr(0xc); say(D[de + 4:de + 8] == b'\0\0\0\0' and (de + 8) in r.fix, 'descriptor at +%x: %d entries, entry pointer present' % (de, struct.unpack_from('<I', D, de + 4)[0]))
    tb = ptr(0x10); say(struct.unpack_from('<I', D, tb)[0] == 0, 'shape table at +%x: 0 entries' % tb)
    say(all(o % 4 == 0 and struct.unpack_from('<I', D, o)[0] < len(D) for o in r.fix), 'every pointer lands inside the chunk')
    for s in ('gameobj_gfx_dis_data', 'pobj_master_gfx_xdata', 'pobj_plac_gfx_xdata'): say(s not in tf, '%s absent' % s)
    fx = sbfw.read_sbf(tf['master_xdata']); x = fx.chunks[-1]; by = fx.byid()
    say(x.z == 0xecdb142b, 'master_xdata root type %08x, %d chunks in the file' % (x.z, len(fx.chunks)))
    cam = x.u32(0xc)
    if cam == 0: say(0xc not in x.ref, 'camera object +0C = 0 (not a reference): 0x5FB25B skips all three lists')
    else:
        c = by[cam]
        for o, nm in ((8, 'intro'), (4, 'trackside'), (0xc, 'postrace')):
            l = by.get(c.u32(o)); cnt = l.u32(4) if l else 0
            say(l is None or (l.u32(0) == 0 and all(l.u32(8 + 8 * k) in (0, 1, 2) for k in range(cnt))), '%s list: %s' % (nm, 'none' if l is None else '%d cameras, kinds %s' % (cnt, sorted({l.u32(8 + 8 * k) for k in range(cnt)}))))
    say(x.u32(0x14) == 0 or x.u32(0x14) in by, 'helicopter +14 = %08x' % x.u32(0x14))
    say(x.u32(8) in by and x.u32(0x18) in by, 'AI map and spline still referenced')
    gfx = sbfw.read_sbf(tf['master_gfx_xdata']); ids = {c.id for c in gfx.chunks} | {c.id for c in fx.chunks} | {c.id for c in g.chunks}
    dangling = [(c.id, v) for f in (gfx, fx, g) for c in f.chunks for v in c.refs() if v and v != 0xffffffff and v not in ids]
    say(not dangling, 'no reference to a chunk that is not in the three files (%d dangling)' % len(dangling))
    print('RESULT', 'all checks passed' if ok else 'PROBLEMS'); return ok

if __name__ == '__main__':
    main(*sys.argv[1:3])
