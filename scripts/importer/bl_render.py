"""Headless Blender render of an OBJ (classic export, or the SR3 result decoded back to OBJ by preview_obj.py).
  blender.exe -b --factory-startup --python bl_render.py -- <obj> <prefix> <centreline.csv in OBJ axes> [view indices...]
Writes <prefix>overview.png and <prefix>road_N.png into work/previews. OBJ (x, y, z) -> Blender (x, -z, y)."""
import bpy, math, mathutils, sys, os
argv = sys.argv[sys.argv.index('--') + 1:]
OBJ, PREFIX, CSV = argv[0], argv[1], argv[2]
VIEWS = [int(v) for v in argv[3:]] or [5, 40, 75, 110, 150, 190, 230, 270]
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'previews')
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
before = set(bpy.data.objects)
bpy.ops.wm.obj_import(filepath=OBJ, forward_axis='NEGATIVE_Z', up_axis='Y')
objs = [o for o in bpy.data.objects if o not in before]
for m in bpy.data.materials:
    if not m.use_nodes: continue
    for n in m.node_tree.nodes:
        if n.type == 'TEX_IMAGE':
            n.interpolation = 'Closest'
        if n.type == 'BSDF_PRINCIPLED':
            n.inputs['Roughness'].default_value = 1.0
            for k in ('Specular IOR Level', 'Specular'):
                if k in n.inputs: n.inputs[k].default_value = 0.0
    try: m.use_backface_culling = False
    except Exception: pass
mn = mathutils.Vector((1e9, 1e9, 1e9)); mx = -mn
for o in objs:
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
ctr = (mn + mx) / 2; size = max(mx.x - mn.x, mx.y - mn.y)
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 2.6
sun.rotation_euler = (math.radians(50), 0, math.radians(30)); sc.collection.objects.link(sun)
w = bpy.data.worlds.new('sky'); w.use_nodes = True
w.node_tree.nodes['Background'].inputs[0].default_value = (0.45, 0.62, 0.85, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 0.6
sc.world = w
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.clip_end = 5000
names = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in names else 'BLENDER_EEVEE'
sc.render.resolution_x = 1280; sc.render.resolution_y = 720; sc.view_settings.view_transform = 'Standard'
def shot(name, pos, target, lens=35):
    cam.location = pos; cam.data.lens = lens
    d = mathutils.Vector(target) - mathutils.Vector(pos)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, name); bpy.ops.render.render(write_still=True)
pts = [tuple(float(v) for v in l.split(',')) for l in open(CSV) if not l.startswith('#')]
P = [mathutils.Vector((p[0], -p[2], p[1])) for p in pts]
def drive(name, i, back=2, ahead=6, up=2.2):
    a = P[(i - back) % len(P)]; b = P[(i + ahead) % len(P)]
    shot(name, (a.x, a.y, a.z + up), (b.x, b.y, b.z + 1.0), 24)
shot(PREFIX + 'overview.png', (ctr.x - size * 0.45, ctr.y - size * 0.6, mx.z + size * 0.4), (ctr.x, ctr.y, ctr.z), 30)
for k, i in enumerate(VIEWS):
    drive(PREFIX + 'road_%d.png' % (k + 1), i)
print('done')
