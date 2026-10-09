"""Blender, headless, on patch.blend: the no-area object goes, faces with more than four corners are cut into triangles, saved in place
(without a .blend1 backup: one of the user's own already has that name)."""
import bpy, bmesh
def area(o): return sum(p.area for p in o.data.polygons)
gone = [o.name for o in bpy.data.objects if 'no area' in o.name]
for n in gone: bpy.data.objects.remove(bpy.data.objects[n], do_unlink=True)
p = bpy.data.objects['patch']; before = (len(p.data.polygons), area(p), sorted({len(q.vertices) for q in p.data.polygons}))
bm = bmesh.new(); bm.from_mesh(p.data); big = [f for f in bm.faces if len(f.verts) > 4]; info = [(len(f.verts), f.calc_area(), tuple(round(c, 2) for c in f.calc_center_median())) for f in big]
# no-area faces that might still be in the patch object (none expected): two pairs of corners in one place
dead = [f for f in bm.faces if f.calc_area() < 1e-6]
if dead: bmesh.ops.delete(bm, geom=dead, context='FACES')
res = bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 4], quad_method='BEAUTY', ngon_method='BEAUTY')
tri = [(len(f.verts), f.calc_area()) for f in res['faces']]
bm.to_mesh(p.data); bm.free(); p.data.update()
m = next((o for o in bpy.data.objects if 'corners were moved' in o.name), None)
if m: m.name = 'patch - original faces with corners moved (as edited)'
for _ in range(3): bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_mainfile()
import collections
print('FIX removed objects:', gone)
print('FIX patch before: %d faces, %.3f m2, corners per face %s' % before)
print('FIX faces with more than four corners:', info, '-> cut into', len(tri), 'triangles of', [round(a, 2) for _, a in tri], 'm2')
print('FIX no-area faces found inside the patch object and removed:', len(dead))
print('FIX patch after: %d faces, %.3f m2, by corners %s ; uv layers %s' % (len(p.data.polygons), area(p), dict(collections.Counter(len(q.vertices) for q in p.data.polygons)), [u.name for u in p.data.uv_layers]))
print('FIX objects in the file now:', [(o.name, len(o.data.polygons)) for o in bpy.data.objects if o.type == 'MESH'])
