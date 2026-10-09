import bpy, bmesh, collections
p = bpy.data.objects['patch']; bm = bmesh.new(); bm.from_mesh(p.data); dead = [f for f in bm.faces if f.calc_area() < 1e-6]; n = len(dead)
bmesh.ops.delete(bm, geom=dead, context='FACES'); loose = [v for v in bm.verts if not v.link_faces]; nl = len(loose); bmesh.ops.delete(bm, geom=loose, context='VERTS')
bm.to_mesh(p.data); bm.free(); p.data.update(); bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_mainfile()
print('FIX2 no-area triangles removed: %d ; loose vertices removed: %d ; patch now %d faces, %.3f m2, by corners %s' % (n, nl, len(p.data.polygons), sum(q.area for q in p.data.polygons), dict(collections.Counter(len(q.vertices) for q in p.data.polygons))))
