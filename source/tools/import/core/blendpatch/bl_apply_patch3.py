"""Blender, headless, on a base course file: the patch is applied from the content of patch.blend alone (its dump, bl_dump.py) and saved.
    blender -b <base.blend> --python bl_apply_patch3.py -- <patch.pkl> <out.blend>
The three patch objects sit in the course object's own frame (same matrix), so the stored numbers are copied as they are - no arithmetic:
  'patch'                         faces to add (material, texture coordinates)
  '... as they were (before)'     original faces some corners of which move, in their original places
  '... (as edited)'               the same faces, same order, same corner order, in their new places
A base face is recognised by the stored numbers of its corners, bit for bit."""
import bpy, bmesh, sys, pickle, collections
import numpy as np
a = sys.argv[sys.argv.index('--') + 1:]
D = pickle.load(open(a[0], 'rb'))
for d in D['objects']:
    for k, v in list(d.items()):
        if isinstance(v, tuple) and len(v) == 4 and v[0] == 'nd': d[k] = np.frombuffer(v[3], v[1]).reshape(v[2])
PT = next(o for o in D['objects'] if o['name'] == 'patch'); BEF = next(o for o in D['objects'] if '(before)' in o['name']); AFT = next(o for o in D['objects'] if '(as edited)' in o['name'])
o = bpy.data.objects['1995 course (RAW2)']; me = o.data; nv0 = len(me.vertices); nf0 = len(me.polygons); M = np.array(o.matrix_world)
for p in (PT, BEF, AFT): assert np.array_equal(p['matrix'], M), 'a patch object is not in the frame of the course object: ' + p['name']
def loops(d, k): s, n = int(d['loop_start'][k]), int(d['loop_total'][k]); return d['loop_vert'][s:s + n], s
b = lambda p: np.ascontiguousarray(p, np.float32).tobytes()
co = np.empty(nv0 * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3); kv = [b(p) for p in co]
ls = np.empty(nf0, np.int32); lt = np.empty(nf0, np.int32); me.polygons.foreach_get('loop_start', ls); me.polygons.foreach_get('loop_total', lt); lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', lv)
byface = collections.defaultdict(list)
for k in range(nf0): byface[frozenset(kv[i] for i in lv[ls[k]:ls[k] + lt[k]])].append(k)
moved = {}; nofind = 0
for j in range(len(BEF['loop_total'])):
    vb, _ = loops(BEF, j); va, _ = loops(AFT, j); B_ = BEF['co_local'][vb]; A_ = AFT['co_local'][va]; ks = byface.get(frozenset(b(p) for p in B_), [])
    if not ks: nofind += 1; continue
    for k in ks:
        for i in lv[ls[k]:ls[k] + lt[k]].tolist():
            for c in range(len(B_)):
                if kv[i] == b(B_[c]) and b(B_[c]) != b(A_[c]): moved[i] = A_[c]
new = co.copy()
for i, w in moved.items(): new[i] = w
me.vertices.foreach_set('co', new.ravel())
bm = bmesh.new(); bm.from_mesh(me); uvl = bm.loops.layers.uv.verify(); slot = {s.material.name: i for i, s in enumerate(o.material_slots) if s.material}
vert = {}; nface = 0; missing = set()
for k in range(len(PT['loop_total'])):
    vi, s = loops(PT, k); vs = []
    for i in vi.tolist():
        key = b(PT['co_local'][i])
        if key not in vert: vert[key] = bm.verts.new(tuple(float(x) for x in PT['co_local'][i]))
        vs.append(vert[key])
    if len(set(vs)) < 3: continue
    f = bm.faces.new(vs); name = PT['mats'][int(PT['mat_index'][k])]
    if name in slot: f.material_index = slot[name]
    else: missing.add(name)
    if PT['uv'] is not None:
        for j, l in enumerate(f.loops): l[uvl].uv = tuple(map(float, PT['uv'][s + j]))
    nface += 1
bm.to_mesh(me); bm.free(); me.update()
g = o.vertex_groups.new(name='PATCH'); g.add(list(range(nv0, len(me.vertices))), 1.0, 'REPLACE')
g2 = o.vertex_groups.new(name='MOVED'); g2.add(sorted(moved), 1.0, 'REPLACE')
bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_as_mainfile(filepath=a[1])
print('APPLY3 moved faces not found in the base: %d ; vertices moved: %d ; patch faces added: %d ; faces %d -> %d, vertices %d -> %d ; materials not found: %s' % (nofind, len(moved), nface, nf0, len(me.polygons), nv0, len(me.vertices), sorted(missing)))
