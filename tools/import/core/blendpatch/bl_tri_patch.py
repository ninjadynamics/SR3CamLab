"""Blender, headless, on patch.blend: every face of the patch becomes triangles; saved in place without a .blend1 backup."""
import bpy, bmesh, collections
p = bpy.data.objects['patch']; a0 = sum(q.area for q in p.data.polygons); n0 = collections.Counter(len(q.vertices) for q in p.data.polygons)
bm = bmesh.new(); bm.from_mesh(p.data)
bmesh.ops.triangulate(bm, faces=[f for f in bm.faces if len(f.verts) > 3], quad_method='BEAUTY', ngon_method='BEAUTY')
dead = [f for f in bm.faces if f.calc_area() < 1e-6]; nd = len(dead)
if dead: bmesh.ops.delete(bm, geom=dead, context='FACES')
bm.to_mesh(p.data); bm.free(); p.data.update()
bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_mainfile()
print('TRI before %s, %.3f m2 ; after %s, %.3f m2 ; no-area triangles removed %d ; other objects: %s' % (dict(n0), a0, dict(collections.Counter(len(q.vertices) for q in p.data.polygons)), sum(q.area for q in p.data.polygons), nd,
      [(o.name, dict(collections.Counter(len(q.vertices) for q in o.data.polygons))) for o in bpy.data.objects if o.type == 'MESH' and o is not p]))
