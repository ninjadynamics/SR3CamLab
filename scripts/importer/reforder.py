"""Chunk order rule of the SBF loader: a chunk may only reference chunks that come EARLIER in the same file.
All six arcade tracks obey it (0 forward references among 50,952 id references of their master_gfx files); the steps
that put authored meshes on the scenery tree did not (the kind 11 chunk stood before its meshes), and the first in-game
run of step34 crashed in 0x5C1EB0 walking exactly that list (149 dangling entries). See 01_container.md.
    python reforder.py                 -> report forward references of every built step in ../out
    python reforder.py fix [step ...]  -> rewrite the files of those steps (default: every step that needs it) with the
                                          chunks in dependency order. Chunk contents, ids, fixups and refs are unchanged.
topo(f) is called by build_testtrack.write_track, so new builds are always ordered."""
import os, sys
from common import *
import sbfw

def forward_refs(f):
    pos = {c.id: i for i, c in enumerate(f.chunks)}
    return sum(1 for i, c in enumerate(f.chunks) for o in c.ref if pos.get(c.u32(o), -1) > i)

def topo(f):
    """stable dependency order: chunks keep their order, except that everything a chunk references is emitted before it.
    The root (last chunk) stays last. Returns the number of chunks that moved."""
    by = f.byid(); done = set(); out = []
    def emit(c):
        stack = [(c, iter([by[v] for v in (c.u32(o) for o in c.ref) if v in by]))]; seen = {c.id}
        while stack:
            cur, it = stack[-1]
            for d in it:
                if d.id not in done and d.id not in seen: seen.add(d.id); stack.append((d, iter([by[v] for v in (d.u32(o) for o in d.ref) if v in by]))); break
            else:
                stack.pop()
                if cur.id not in done: done.add(cur.id); out.append(cur)
    for c in f.chunks: emit(c)
    assert len(out) == len(f.chunks) and out[-1] is f.chunks[-1], 'root must stay last'
    moved = sum(1 for a, b in zip(out, f.chunks) if a is not b); f.chunks = out
    assert forward_refs(f) == 0
    return moved

def steps():
    for s in sorted(os.listdir(OUT)):
        for slot in ('Desert4', 'Stadium4'):
            d = os.path.join(OUT, s, slot)
            if os.path.isdir(d): yield s, d

def main(argv):
    fix = argv[:1] == ['fix']; only = set(argv[1:])
    for s, d in steps():
        if only and s not in only: continue
        for fn in sorted(os.listdir(d)):
            if not fn.lower().endswith('.sbf'): continue
            p = os.path.join(d, fn); f = sbfw.read_sbf(p); n = forward_refs(f)
            if not n: continue
            if not fix: print('%-48s %-48s %d forward references' % (s, fn, n)); continue
            before = [(c.kind, c.id, c.data, tuple(c.fix), tuple(c.ref), c.z) for c in f.chunks]
            for c in f.chunks: c.gap = None
            moved = topo(f); b = sbfw.write_sbf(f, compress=True, layout='auto', level=6); g = sbfw.read_sbf(b)
            after = [(c.kind, c.id, c.data, tuple(c.fix), tuple(c.ref), c.z) for c in g.chunks]
            assert sorted(before, key=lambda t: t[1]) == sorted(after, key=lambda t: t[1]) and forward_refs(g) == 0
            open(p, 'wb').write(b); print('%-48s %-48s fixed: %d forward references, %d chunks moved, contents identical' % (s, fn, n, moved))

if __name__ == '__main__':
    main(sys.argv[1:])
