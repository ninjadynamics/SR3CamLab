"""Headless Blender fly-through of a classic course (frames; resumable: existing frames are skipped).
  blender -b --factory-startup --python bl_fly.py -- <frames dir> <prefix> <centreline.csv> <obj> [--frames 450] [--speed 55] [--up 3] [--start 0] [--sky r,g,b]
(old header follows) (unlit: the tiles already hold the game's colours).
  blender -b --factory-startup --python bl_course.py -- <out dir> <prefix> <centreline.csv (OBJ axes)> <obj> [more obj ...] [--views N] [--up 2.2] [--only overview|road]
Writes <prefix>overview.png and <prefix>road_1..N.png. OBJ (x, y, z) -> Blender (x, -z, y)."""
import bpy, math, mathutils, sys, os
argv = sys.argv[sys.argv.index('--') + 1:]
def opt(name, default):
    if name in argv:
        i = argv.index(name); v = argv[i + 1]; del argv[i:i + 2]; return v
    return default
NF = int(opt('--frames', 450)); SPEED = float(opt('--speed', 55)); START = float(opt('--start', 0)); NV = 8; UP = float(opt('--up', 2.2)); ONLY = opt('--only', ''); SKYCOL = opt('--sky', '0.40,0.52,0.85')
OUT, PREFIX, CSV = argv[0], argv[1], argv[2]; OBJS = argv[3:]
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
main_objs = []
for k, p in enumerate(OBJS):
    before = set(bpy.data.objects); bpy.ops.wm.obj_import(filepath=p, forward_axis='NEGATIVE_Z', up_axis='Y')
    if k == 0: main_objs = [o for o in bpy.data.objects if o not in before]
def unlit(m):
    m.use_nodes = True; nt = m.node_tree; img = None; col = (0.8, 0.8, 0.8, 1)
    for n in nt.nodes:
        if n.type == 'TEX_IMAGE' and n.image is not None and img is None: img = n.image
        if n.type == 'BSDF_PRINCIPLED': col = tuple(n.inputs['Base Color'].default_value)
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial'); em = nt.nodes.new('ShaderNodeEmission')
    try: m.use_backface_culling = False
    except Exception: pass
    if img is None: em.inputs[0].default_value = col; nt.links.new(em.outputs[0], out.inputs[0]); return
    tex = nt.nodes.new('ShaderNodeTexImage'); tex.image = img; tex.interpolation = 'Closest'; nt.links.new(tex.outputs[0], em.inputs[0])
    if img.depth == 32:
        tr = nt.nodes.new('ShaderNodeBsdfTransparent'); mix = nt.nodes.new('ShaderNodeMixShader')
        nt.links.new(tex.outputs[1], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs[0])
        try: m.surface_render_method = 'DITHERED'
        except Exception: pass
    else: nt.links.new(em.outputs[0], out.inputs[0])
for m in bpy.data.materials: unlit(m)
mn = mathutils.Vector((1e9, 1e9, 1e9)); mx = -mn
for o in main_objs:
    for c in o.bound_box:
        w = o.matrix_world @ mathutils.Vector(c)
        mn = mathutils.Vector(map(min, mn, w)); mx = mathutils.Vector(map(max, mx, w))
ctr = (mn + mx) / 2; size = max(mx.x - mn.x, mx.y - mn.y)
w = bpy.data.worlds.new('sky'); w.use_nodes = True
r, g, b = [float(x) for x in SKYCOL.split(',')]
w.node_tree.nodes['Background'].inputs[0].default_value = (r, g, b, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 1.0
sc.world = w
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam
cam.data.clip_start = 0.3; cam.data.clip_end = 600000
names = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in names else 'BLENDER_EEVEE'
try: sc.eevee.taa_render_samples = 12
except Exception: pass
sc.render.resolution_x = 1280; sc.render.resolution_y = 720; sc.view_settings.view_transform = 'Standard'

sc.render.image_settings.file_format = 'JPEG'; sc.render.image_settings.quality = 92
pts = [tuple(float(v) for v in l.split(',')[:3]) for l in open(CSV) if not l.startswith('#') and l.strip()]
P0 = [mathutils.Vector((p[0], -p[2], p[1])) for p in pts]; M = len(P0)
def smooth(P, r): return [sum((P[(i + k) % M] for k in range(-r, r + 1)), mathutils.Vector()) / (2 * r + 1) for i in range(M)]
PATH = smooth(P0, 2)
cum = [0.0]
for i in range(M): cum.append(cum[-1] + (PATH[(i + 1) % M] - PATH[i]).length)
TOTAL = cum[-1]
def cr(t):
    i = int(math.floor(t)); f = t - i; p0, p1, p2, p3 = (PATH[(i + k) % M] for k in (-1, 0, 1, 2))
    return 0.5 * ((2 * p1) + (-p0 + p2) * f + (2 * p0 - 5 * p1 + 4 * p2 - p3) * f * f + (-p0 + 3 * p1 - 3 * p2 + p3) * f ** 3)
def at_dist(d):
    d %= TOTAL; lo = 0
    while cum[lo + 1] < d: lo += 1
    return cr(lo + (d - cum[lo]) / max(cum[lo + 1] - cum[lo], 1e-6))
cam.data.lens = 22
os.makedirs(OUT, exist_ok=True)
for f in range(NF):
    fn = os.path.join(OUT, '%s%04d.jpg' % (PREFIX, f))
    if os.path.exists(fn): continue
    d = START + f * SPEED / 30.0; a = at_dist(d); b = at_dist(d + 28.0)
    cam.location = (a.x, a.y, a.z + UP); dv = mathutils.Vector((b.x, b.y, b.z + UP * 0.6)) - cam.location
    cam.rotation_euler = dv.to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = fn; bpy.ops.render.render(write_still=True)
print('done')
