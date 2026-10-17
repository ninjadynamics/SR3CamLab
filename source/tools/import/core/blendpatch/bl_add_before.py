"""Blender, headless, on patch.blend: the 'before' object, in the course object's own frame (same matrix, the base file's stored numbers)."""
import bpy, sys, pickle
from mathutils import Matrix
D = pickle.load(open(sys.argv[sys.argv.index('--') + 1], 'rb')); before = D['before']; name = 'patch - the same original faces as they were (before)'
if name in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
V = []; F = []
for P in before: k = len(V); V += P; F.append(tuple(range(k, k + len(P))))
me = bpy.data.meshes.new(name); me.from_pydata(V, [], F); me.update(); o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o); o.matrix_world = Matrix(D['matrix'])
for _ in range(3): bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_mainfile(); print('BEFORE added:', [(x.name, len(x.data.polygons)) for x in bpy.data.objects if x.type == 'MESH'])
