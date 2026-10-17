"""Blender, headless, on mountain_patched.blend: keep only the faces of the diff, as three objects, and save patch.blend.
    blender -b mountain_patched.blend --python bl_make_patch.py -- <final.pkl> <out.blend>"""
import bpy, bmesh, sys, pickle
a = sys.argv[sys.argv.index('--') + 1:]; K = pickle.load(open(a[0], 'rb')); OUT = a[1]
src = bpy.data.objects['1995 course (RAW2)']
for o in list(bpy.data.objects):
    if o is not src: bpy.data.objects.remove(o, do_unlink=True)
sets = (('patch', K['good']), ('not in the patch - faces with no area', K['deg']), ('not in the patch - original faces whose corners were moved', K['moved']))
made = []
for name, idx in sets:
    if not idx: continue
    o = src.copy(); o.data = src.data.copy(); o.name = name; o.data.name = name; bpy.context.scene.collection.objects.link(o)
    bm = bmesh.new(); bm.from_mesh(o.data); bm.faces.ensure_lookup_table(); keep = set(idx)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context='FACES'); bm.to_mesh(o.data); bm.free()
    made.append((name, len(o.data.polygons), len(o.data.vertices)))
bpy.data.objects.remove(src, do_unlink=True)
for o in bpy.data.objects:                                              # only the materials each object still uses
    used = sorted({p.material_index for p in o.data.polygons}); slots = [o.material_slots[i].material for i in used]; remap = {old: new for new, old in enumerate(used)}
    for p in o.data.polygons: p.material_index = remap[p.material_index]
    o.data.materials.clear()
    for m in slots: o.data.materials.append(m)
for _ in range(4): bpy.ops.outliner.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print('patch.blend:', made, '; materials kept', len(bpy.data.materials), '; images kept', len(bpy.data.images))
