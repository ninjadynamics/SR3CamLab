"""Headless Blender preview of a classic course (unlit: the tiles already hold the game's colours).
  blender -b --factory-startup --python bl_course.py -- <out dir> <prefix> <centreline.csv (OBJ axes)> <obj> [more obj ...] [--views N] [--up 2.2] [--only overview|road]
Writes <prefix>overview.png and <prefix>road_1..N.png. OBJ (x, y, z) -> Blender (x, -z, y)."""
import bpy, math, mathutils, sys, os
argv = sys.argv[sys.argv.index('--') + 1:]
def opt(name, default):
    if name in argv:
        i = argv.index(name); v = argv[i + 1]; del argv[i:i + 2]; return v
    return default
NV = int(opt('--views', 8)); UP = float(opt('--up', 2.2)); ONLY = opt('--only', ''); SKYCOL = opt('--sky', '0.40,0.52,0.85')
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
def shot(name, pos, target, lens=35):
    cam.location = pos; cam.data.lens = lens
    d = mathutils.Vector(target) - mathutils.Vector(pos)
    cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, name); bpy.ops.render.render(write_still=True)
pts = [tuple(float(v) for v in l.split(',')[:3]) for l in open(CSV) if not l.startswith('#') and l.strip()]
Pp = [mathutils.Vector((p[0], -p[2], p[1])) for p in pts]; n = len(Pp)
def at(i, d):
    """point d metres ahead of point i along the line"""
    j = i; acc = 0.0; step = 1 if d >= 0 else -1; d = abs(d)
    while acc < d and abs(j - i) < n:
        a = Pp[j % n]; b = Pp[(j + step) % n]; acc += (b - a).length; j += step
    return Pp[j % n]
if ONLY != 'road': shot(PREFIX + 'overview.png', (ctr.x - size * 0.45, ctr.y - size * 0.6, mx.z + size * 0.4), (ctr.x, ctr.y, ctr.z), 30)
if ONLY != 'overview':
    for k in range(NV):
        i = (k * n) // NV + 2; a = at(i, -6); b = at(i, 25)
        shot(PREFIX + 'road_%d.png' % (k + 1), (a.x, a.y, a.z + UP), (b.x, b.y, b.z + 1.0), 24)
print('done')
