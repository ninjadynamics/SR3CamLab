"""Blender, headless: OBJ files (with their MTL and pictures) into one .blend, every picture packed into it.
    blender -b --factory-startup --python bl_obj_to_blend.py -- <out.blend> <a.obj> [<b.obj> ...]
The OBJ axes are the course export's (x, y, -gameZ), read with -Z forward and Y up as the Blender patch files are; pictures are drawn
unfiltered (the 1995 look) and the view starts flat-shaded with textures."""
import bpy, sys, os
a = sys.argv[sys.argv.index('--') + 1:]; OUT = a[0]; OBJS = a[1:]
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
for p in OBJS:
    bpy.ops.wm.obj_import(filepath=p, forward_axis='NEGATIVE_Z', up_axis='Y')
    for ob in bpy.context.selected_objects: ob.name = os.path.splitext(os.path.basename(p))[0] + ('' if len(bpy.context.selected_objects) == 1 else ' ' + ob.name)
for m in bpy.data.materials:
    if not m.use_nodes: continue
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE': n.interpolation = 'Closest'
        if n.type == 'BSDF_PRINCIPLED':
            n.inputs['Roughness'].default_value = 1.0
            for k in ('Specular IOR Level', 'Specular'):
                if k in n.inputs: n.inputs[k].default_value = 0.0
bpy.ops.file.pack_all()
for scr in bpy.data.screens:
    for area in scr.areas:
        if area.type == 'VIEW_3D':
            sp = area.spaces[0]; sp.shading.type = 'SOLID'; sp.shading.light = 'FLAT'; sp.shading.color_type = 'TEXTURE'; sp.clip_end = 6000.0; sp.clip_start = 0.2
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=OUT); print('saved ' + OUT)
