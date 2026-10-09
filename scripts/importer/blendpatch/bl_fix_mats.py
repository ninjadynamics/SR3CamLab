import bpy, sys, pickle, collections
names = pickle.load(open(sys.argv[sys.argv.index('--') + 1], 'rb')); p = bpy.data.objects['patch']; me = p.data; assert len(names) == len(me.polygons)
slot = {s.material.name: i for i, s in enumerate(p.material_slots) if s.material}; missing = sorted(set(names) - set(slot))
for nm in missing: me.materials.append(bpy.data.materials[nm]); slot[nm] = len(me.materials) - 1
for q, nm in zip(me.polygons, names): q.material_index = slot[nm]
me.update(); bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_mainfile()
print('MATS set on %d faces: %s ; slots that had to be added back: %s' % (len(names), dict(collections.Counter(p.material_slots[q.material_index].material.name for q in me.polygons)), missing))
