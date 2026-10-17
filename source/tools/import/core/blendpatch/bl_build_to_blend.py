"""Blender: a build decoded back from the game files (preview_obj.py) as a scene to inspect. Two objects: the 1995 course, and the game's own road apart.
    blender -b --factory-startup --python bl_build_to_blend.py -- <decoded.obj> <out.blend> [<patch.json>]
With the patch file: the faces of the patch are in vertex group PATCH and selected (edit mode shows them)."""
import bpy, bmesh, sys, json
import numpy as np
_a = sys.argv[sys.argv.index('--') + 1:]; OBJ = _a[0]; OUT = _a[1]; PATCH = _a[2] if len(_a) > 2 else None
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.wm.obj_import(filepath=OBJ, forward_axis='NEGATIVE_Z', up_axis='Y')
ob = bpy.context.selected_objects[0]; ob.name = '1995 course (RAW2)'
for m in bpy.data.materials:
    if not m.use_nodes: continue
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE': n.interpolation = 'Closest'
        if n.type == 'BSDF_PRINCIPLED':
            n.inputs['Roughness'].default_value = 1.0
            for k in ('Specular IOR Level', 'Specular'):
                if k in n.inputs: n.inputs[k].default_value = 0.0
# the game's own road (materials that are not the importer's c1a..... textures) into an object of its own
bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode='EDIT'); bm = bmesh.from_edit_mesh(ob.data)
road = {i for i, s in enumerate(ob.material_slots) if s.material and not s.material.name.startswith('tex_c1a')}
for f in bm.faces: f.select = f.material_index in road
bmesh.update_edit_mesh(ob.data)
if any(f.select for f in bm.faces): bpy.ops.mesh.separate(type='SELECTED')
bpy.ops.object.mode_set(mode='OBJECT')
for o in bpy.data.objects:
    if o is not ob and o.type == 'MESH': o.name = "SR3 road (the game's own - hide with H)"; o.color = (1.0, 0.3, 0.0, 1.0)
for o in bpy.data.objects: o.select_set(False)
ob.select_set(True)
bpy.ops.file.pack_all()
for scr in bpy.data.screens:
    for area in scr.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces[0]; sp.shading.type = 'SOLID'; sp.shading.light = 'FLAT'; sp.shading.color_type = 'TEXTURE'; sp.clip_end = 6000.0; sp.clip_start = 0.2; sp.overlay.show_floor = False; sp.overlay.show_axis_x = False; sp.overlay.show_axis_y = False
if PATCH:
    J = json.load(open(PATCH)); me = ob.data; co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3).astype(np.float64)
    pts = np.array([p for f_ in J['add'] for p in f_['p']], float); near = [set(np.nonzero(np.linalg.norm(co - p, axis=1) < 0.002)[0].tolist()) for p in pts]
    faces = [near[3 * k] | near[3 * k + 1] | near[3 * k + 2] for k in range(len(J['add']))]; cand = set().union(*faces); hit = set(); n = 0
    for pl in me.polygons:
        vs = set(pl.vertices); pl.select = False
        if vs <= cand and any(vs <= f for f in faces): pl.select = True; hit |= vs; n += 1
    ob.vertex_groups.new(name='PATCH').add(sorted(hit), 1.0, 'REPLACE'); print('PATCH faces marked: %d of %d' % (n, len(J['add'])))
bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_as_mainfile(filepath=OUT); print('saved ' + OUT)
