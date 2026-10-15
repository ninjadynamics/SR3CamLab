import sys, collections, struct
from common import *
folder = sys.argv[1] if len(sys.argv) > 1 else os.path.join(TRACKS, 'Stadium4')
full = len(sys.argv) > 2
for suf, p in sorted(track_files(folder).items()):
    if suf == 'proc': print('proc', os.path.getsize(p)); continue
    s = Sbf(p)
    print('==', os.path.basename(p), 'raw', len(s.d), 'hdr', ['%x' % x for x in s.hdr], 'chunks', len(s.chunks))
    cnt = collections.Counter()
    for c in s.chunks:
        cnt[(c.kind, c.z if c.kind == 12 else 0)] += 1
        if c.kind in (5, 6, 7, 11, 12) or full:
            d = s.bytes(c)
            refs = [struct.unpack_from('<I', d, o)[0] for o in c.ref]
            print('  k%2d id %08x z %08x size %8d nfix %5d nref %3d  off %x  %s' % (c.kind, c.id, c.z, c.size, len(c.fix), len(c.ref), c.off, d[:24].hex() if c.kind != 12 else d[:64].hex()))
    print('  counts', sorted(cnt.items()))
