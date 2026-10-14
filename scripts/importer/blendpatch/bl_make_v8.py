"""Blender, headless: an edited scene that went through a whole-mesh Merge by Distance, repaired and saved under a new name.
    blender -b --factory-startup --python bl_make_v8.py -- <scene as built.blend> <edited scene.blend> <out.blend>
1. the faces the merge took (one side of every back-to-back pair: tree blades) are put back from the scene as built, each on corners of its own;
2. corners at the same place are welded, except where that would lay one face on another's corners or close a face up;
3. faces with no area, and edges and corners that belong to no face, are removed.
Nothing else is touched."""
import bpy, bmesh, sys, collections
a = sys.argv[sys.argv.index('--') + 1:]; BUILT, EDITED, OUT = a[:3]; NAME = '1995 course (RAW2)'; DIST = 0.0001
rk = lambda co: (round(co.x, 4), round(co.y, 4), round(co.z, 4))
def read(path):
    bpy.ops.wm.open_mainfile(filepath=path); o = bpy.data.objects[NAME]; bm = bmesh.new(); bm.from_mesh(o.data); uvl = bm.loops.layers.uv.verify(); F = []
    for f in bm.faces: F.append((o.material_slots[f.material_index].material.name, [tuple(l.vert.co) for l in f.loops], [tuple(l[uvl].uv) for l in f.loops]))
    bm.free(); return F
cset = lambda P: frozenset((round(p[0], 4), round(p[1], 4), round(p[2], 4)) for p in P)
near = lambda P: frozenset((round(p[0] * 500), round(p[1] * 500), round(p[2] * 500)) for p in P)      # 2 mm cells: the merge shifts a corner by up to its 0.1 mm
B = read(BUILT)
# what Merge by Distance takes from the scene as built: of the faces that share one set of corners, all but the first
seen = set(); lost = []
for m, P, U in B:
    k = cset(P)
    if len(k) < 3: continue
    if k in seen: lost.append((m, P, U))
    else: seen.add(k)
print('V8 scene as built: %d faces ; laid on the corners of another face (what the merge takes): %d' % (len(B), len(lost)))
bpy.ops.wm.open_mainfile(filepath=EDITED); o = bpy.data.objects[NAME]; me = o.data; slot = {s.material.name: i for i, s in enumerate(o.material_slots) if s.material}
bm = bmesh.new(); bm.from_mesh(me); uvl = bm.loops.layers.uv.verify(); n0 = (len(bm.verts), len(bm.edges), len(bm.faces))
have = collections.defaultdict(list)
from mathutils import kdtree
VL = list(bm.verts); kd = kdtree.KDTree(len(VL))
for i_, v in enumerate(VL): kd.insert(v.co, i_)
kd.balance()
def twins_of(P):
    """faces of the edited scene standing on these very corners (within 0.5 mm: the merge shifts a corner by up to its 0.1 mm)"""
    S_ = [{VL[i] for _, i, _ in kd.find_range(p, 0.0005)} for p in P]
    if not all(S_): return []
    return [f for f in {f for v in S_[0] for f in v.link_faces} if len(f.verts) == len(P) and all(any(v in s for v in f.verts) for s in S_)]
# 1. the lost sides back, where the side that stayed is still there untouched
back = []; skipped = collections.Counter(); guard = set()
for m, P, U in lost:
    twins = twins_of(P)
    if not twins: skipped['its other side is no longer in the edited scene (moved or removed by hand)'] += 1; continue
    vs = [bm.verts.new(p) for p in P]; f = bm.faces.new(vs); f.material_index = slot[m]
    for l, u in zip(f.loops, U): l[uvl].uv = u
    back.append(f); guard.update(vs)
    for t in twins: guard.update(t.verts)
bm.normal_update()
# a side that was put back although the edited scene still had it (the merge left that pair alone) would be a third face: none may exist
trip = 0
print('V8 sides put back: %d ; left out: %s' % (len(back), dict(skipped)))
# 2. corners at the same place welded (never a guarded corner: a back-to-back pair needs corners of its own on one side)
cand = [v for v in bm.verts if v not in guard]; tm = bmesh.ops.find_doubles(bm, verts=cand, dist=DIST)['targetmap']
def bad_faces(tm):
    out = set(); seenk = {}
    for f in bm.faces:
        vs = [tm.get(v, v) for v in f.verts]; k = frozenset(vs)
        if len(k) < 3: continue                                        # closes up: it had no area (step 3 takes it)
        if len(k) < len(vs) and f.calc_area() > 1e-8: out.add(f); continue
        if k in seenk and seenk[k] is not f: out.add(f); out.add(seenk[k])
        else: seenk[k] = f
    return out
held = 0
for _ in range(6):
    bad = bad_faces(tm)
    if not bad: break
    drop = {v for f in bad for v in f.verts}; drop |= {t for t in tm.values() if t in drop}
    for v in [v for v, t in tm.items() if v in drop or t in drop]: del tm[v]; held += 1
nw = len(tm); bmesh.ops.weld_verts(bm, targetmap=tm)
# 3. no face without area, nothing loose
zero = [f for f in bm.faces if f.calc_area() < 1e-8]; nz = len(zero); bmesh.ops.delete(bm, geom=zero, context='FACES_ONLY')
le = [e for e in bm.edges if not e.link_faces]; nle = len(le); bmesh.ops.delete(bm, geom=le, context='EDGES')
lv = [v for v in bm.verts if not v.link_faces]; nlv = len(lv); bmesh.ops.delete(bm, geom=lv, context='VERTS')
bm.normal_update()
# what is left to know
thin = sum(1 for f in bm.faces if 2 * f.calc_area() / max(e.calc_length() for e in f.edges) < 0.01); ng = collections.Counter(len(f.verts) for f in bm.faces)
loc = collections.Counter(rk(v.co) for v in bm.verts); same = sum(n - 1 for n in loc.values() if n > 1)
al = sum(1 for f in bm.faces if o.material_slots[f.material_index].material.name.endswith('_a'))
pairs = collections.Counter(cset([v.co for v in f.verts]) for f in bm.faces); np_ = sum(1 for n in pairs.values() if n == 2); n3 = sum(1 for n in pairs.values() if n > 2)
n1 = (len(bm.verts), len(bm.edges), len(bm.faces)); bm.to_mesh(me); bm.free(); me.update()
for pl in me.polygons: pl.select = False
bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_as_mainfile(filepath=OUT)
print('V8 corners welded: %d (held back because the weld would lay a face on another or fold one: %d) ; faces with no area removed: %d ; loose edges %d, loose corners %d removed' % (nw, held, nz, nle, nlv))
print('V8 corners %d -> %d ; edges %d -> %d ; faces %d -> %d ; see-through faces now %d ; back-to-back pairs %d, places with three or more faces on the same corners %d' % (n0[0], n1[0], n0[1], n1[1], n0[2], n1[2], al, np_, n3))
print('V8 corners still sharing a place with another corner: %d ; faces thinner than 1 cm: %d ; faces by number of corners: %s ; saved %s' % (same, thin, dict(sorted(ng.items())), OUT))
