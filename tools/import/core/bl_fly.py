"""Headless Blender: one lap along the centre line as JPEG frames (resumable: existing frames are skipped).
  blender.exe -b --factory-startup --python bl_fly.py -- <obj> <outdir> <centreline.csv> <frames> [first] [last]
Adapted from the coordinator's fly.py (no sky model; plain sky colour). Assemble with fly_all.py."""
import bpy, math, mathutils, sys, os
argv = sys.argv[sys.argv.index('--') + 1:]
OBJ, OUT, CSV, N = argv[0], argv[1], argv[2], int(argv[3])
F0 = int(argv[4]) if len(argv) > 4 else 0; F1 = int(argv[5]) if len(argv) > 5 else N
os.makedirs(OUT, exist_ok=True); sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.wm.obj_import(filepath=OBJ, forward_axis='NEGATIVE_Z', up_axis='Y')
for m in bpy.data.materials:
    if not m.use_nodes: continue
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE': n.interpolation = 'Linear'
        if n.type == 'BSDF_PRINCIPLED':
            n.inputs['Roughness'].default_value = 1.0
            for k in ('Specular IOR Level', 'Specular'):
                if k in n.inputs: n.inputs[k].default_value = 0.0
    try: m.use_backface_culling = False
    except Exception: pass
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(30)); sc.collection.objects.link(sun)
w = bpy.data.worlds.new('sky'); w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.42, 0.63, 0.92, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.9
sc.world = w
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.clip_end = 6000; cam.data.clip_start = 0.5; cam.data.lens = 20; cam.data.sensor_fit = 'HORIZONTAL'
names = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in names else 'BLENDER_EEVEE'
try: sc.eevee.taa_render_samples = 12
except Exception: pass
sc.render.resolution_x = 1280; sc.render.resolution_y = 720; sc.view_settings.view_transform = 'Standard'
sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 92
pts = [tuple(float(v) for v in l.split(',')) for l in open(CSV) if not l.startswith('#')]
P = [mathutils.Vector((p[0], -p[2], p[1])) for p in pts]; M = len(P)
def smooth(P, r): return [sum((P[(i + k) % M] for k in range(-r, r + 1)), mathutils.Vector()) / (2 * r + 1) for i in range(M)]
PATH = smooth(P, 1); LOOK = smooth(P, 5)
def at(L, t):
    i = int(math.floor(t)); f = t - i; a, b, c, d = (L[(i + k) % M] for k in (-1, 0, 1, 2))
    return 0.5 * ((2 * b) + (-a + c) * f + (2 * a - 5 * b + 4 * c - d) * f * f + (-a + 3 * b - 3 * c + d) * f ** 3)
for fr in range(F0, F1):
    fp = os.path.join(OUT, 'f%05d.jpg' % fr)
    if os.path.exists(fp): continue
    t = 2.0 + fr / N * M; ease = min(1.0, fr / 60.0); up = 3.2 + (1 - ease) ** 2 * 22
    pos = at(PATH, t); tgt = at(LOOK, t + 7.5); cam.location = (pos.x, pos.y, pos.z + up)
    d = mathutils.Vector((tgt.x, tgt.y, tgt.z + 1.6)) - cam.location; cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = fp; bpy.ops.render.render(write_still=True)
print('done', F0, F1)
