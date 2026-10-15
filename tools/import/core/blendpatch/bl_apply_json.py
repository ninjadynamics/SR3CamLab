"""Blender, headless, on a base course scene: the patch FILE (JSON, patch_to_json.py) is applied and the result saved.
    blender -b <base.blend> --python bl_apply_json.py -- <patch.json> <texmap.json> <out.blend>
Nothing else is read: no patch.blend, no dump. A base that is not the one the patch was made on is refused."""
import bpy, bmesh, sys, json, hashlib, collections
import numpy as np
a = sys.argv[sys.argv.index('--') + 1:]; J = json.load(open(a[0])); M = json.load(open(a[1])); OUT = a[2]
assert J.get('format') == 'sr3lab course patch' and J.get('version') == 1, 'not a course patch file this tool knows'
mat_of = {v['tile']: 'tex_%08x' % int(k) for k, v in M['scenery'].items()}
o = bpy.data.objects['1995 course (RAW2)']; me = o.data; nv0 = len(me.vertices); nf0 = len(me.polygons)
co = np.empty(nv0 * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
b = J['base']; got = hashlib.sha1(co.tobytes()).hexdigest()
if 'scene_vertices_sha1' in b and b['scene_vertices_sha1'] != got: raise SystemExit('REFUSED: this scene is not the base the patch was made on (vertices %d, fingerprint %s; the patch wants %d, %s)' % (nv0, got[:12], b.get('scene_vertices', -1), b['scene_vertices_sha1'][:12]))
key = lambda p: np.asarray(p, np.float32).tobytes()
kv = [key(p) for p in co]
ls = np.empty(nf0, np.int32); lt = np.empty(nf0, np.int32); me.polygons.foreach_get('loop_start', ls); me.polygons.foreach_get('loop_total', lt); lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', lv)
byface = collections.defaultdict(list)
for k in range(nf0): byface[frozenset(kv[i] for i in lv[ls[k]:ls[k] + lt[k]])].append(k)
moved = {}; nofind = 0
for m in J['move']:
    B_ = [key(p) for p in m['before']]; A_ = m['after']; ks = byface.get(frozenset(B_), [])
    if not ks: nofind += 1; continue
    for k in ks:
        for i in lv[ls[k]:ls[k] + lt[k]].tolist():
            for c in range(len(B_)):
                if kv[i] == B_[c] and B_[c] != key(A_[c]): moved[i] = np.asarray(A_[c], np.float32)
if nofind: raise SystemExit('REFUSED: %d of the faces whose corners move are not in this scene' % nofind)
new = co.copy()
for i, w in moved.items(): new[i] = w
me.vertices.foreach_set('co', new.ravel())
bm = bmesh.new(); bm.from_mesh(me); uvl = bm.loops.layers.uv.verify(); slot = {s.material.name: i for i, s in enumerate(o.material_slots) if s.material}
vert = {}; nface = 0
for f_ in J['add']:
    vs = []
    for p in f_['p']:
        k = key(p)
        if k not in vert: vert[k] = bm.verts.new(tuple(float(x) for x in np.asarray(p, np.float32)))
        vs.append(vert[k])
    if len(set(vs)) < 3: continue
    f = bm.faces.new(vs); f.material_index = slot[mat_of[f_['tile']]]
    for j, l in enumerate(f.loops): l[uvl].uv = tuple(float(x) for x in np.asarray(f_['uv'][j], np.float32))
    nface += 1
bm.to_mesh(me); bm.free(); me.update()
g = o.vertex_groups.new(name='PATCH'); g.add(list(range(nv0, len(me.vertices))), 1.0, 'REPLACE')
g2 = o.vertex_groups.new(name='MOVED'); g2.add(sorted(moved), 1.0, 'REPLACE')
bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_as_mainfile(filepath=OUT)
print('APPLYJSON base accepted (fingerprint %s) ; vertices moved: %d ; faces added: %d ; faces %d -> %d, vertices %d -> %d' % (got[:12], len(moved), nface, nf0, len(me.polygons), nv0, len(me.vertices)))
