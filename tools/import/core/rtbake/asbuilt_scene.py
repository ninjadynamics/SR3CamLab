"""Background Blender (factory): the decoded BUILT track (asbuilt_decode.py) as a scene - its own triangles, pictures and light maps, the 1995 sky dome
as the game has it - and stills of it.   blender -b --factory-startup --python asbuilt_scene.py -- <asbuilt dir> <views.json> <out dir> [<save .blend>]
Every material: picture x light map (white where the build gives none: cut-outs, the sea), then the same brightness / saturation / contrast
group as the RT scenes (RT_GAIN, RT_CONTRAST, RT_SAT, RT_SKYSAT in the environment). Drawn two-sided, as the game draws the course."""
import bpy, sys, os, json, math, glob
import numpy as np
from mathutils import Vector
def _classic():
    """<data_root>/classic from tools/import/settings.json (Blender runs this file on its own, without common.py)"""
    try: d = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'settings.json'), encoding='utf-8-sig')).get('data_root')
    except (OSError, ValueError): d = None
    return os.path.join(d or os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '..', '..', 'data'), 'classic')
a = sys.argv[sys.argv.index('--') + 1:]; SRC, VIEWS, OUT = a[0], a[1], a[2]; SAVE = a[3] if len(a) > 3 else None; os.makedirs(OUT, exist_ok=True)
D = np.load(os.path.join(SRC, 'asbuilt.npz')); P = D['P']; U0 = D['U0']; U1 = D['U1']; TEX = D['TEX']; LMP = D['LMP']; CUT = D['CUT']; ONE = D['ONE']; n = len(P)
SHADE = os.environ.get('RT_SHADE', '') == '1'; GAIN = float(os.environ.get('RT_GAIN', '8')); CONTRAST = float(os.environ.get('RT_CONTRAST', '1.15')); SAT = float(os.environ.get('RT_SAT', '1.15')); SKYSAT = float(os.environ.get('RT_SKYSAT', '2.2'))
for o in list(bpy.data.objects): bpy.data.objects.remove(o)
W = np.stack([P[..., 0], -P[..., 2], P[..., 1]], -1).reshape(-1, 3); me = bpy.data.meshes.new('as built'); me.from_pydata(W.tolist(), [], np.arange(3 * n).reshape(-1, 3).tolist()); me.update()
me.uv_layers.new(name='UVMap').data.foreach_set('uv', U0.reshape(-1, 2).ravel()); me.uv_layers.new(name='LM').data.foreach_set('uv', U1.reshape(-1, 2).ravel()); me.uv_layers.active = me.uv_layers['UVMap']
grp = bpy.data.node_groups.new('RT look', 'ShaderNodeTree'); grp.interface.new_socket('Picture', in_out='INPUT', socket_type='NodeSocketColor'); grp.interface.new_socket('Light', in_out='INPUT', socket_type='NodeSocketColor'); grp.interface.new_socket('Colour', in_out='OUTPUT', socket_type='NodeSocketColor')
gn = grp.nodes; gl = grp.links; gi_ = gn.new('NodeGroupInput'); go_ = gn.new('NodeGroupOutput'); mul = gn.new('ShaderNodeMix'); mul.data_type = 'RGBA'; mul.blend_type = 'MULTIPLY'; mul.inputs['Factor'].default_value = 1.0; gl.new(gi_.outputs['Picture'], mul.inputs['A']); gl.new(gi_.outputs['Light'], mul.inputs['B'])
sc_ = gn.new('ShaderNodeVectorMath'); sc_.operation = 'SCALE'; sc_.inputs['Scale'].default_value = GAIN; gl.new(mul.outputs['Result'], sc_.inputs[0]); hs = gn.new('ShaderNodeHueSaturation'); hs.inputs['Saturation'].default_value = SAT; gl.new(sc_.outputs['Vector'], hs.inputs['Color'])
sp = gn.new('ShaderNodeSeparateColor'); gl.new(hs.outputs['Color'], sp.inputs['Color']); cb = gn.new('ShaderNodeCombineColor')
for ci in range(3):
    d_ = gn.new('ShaderNodeMath'); d_.operation = 'DIVIDE'; d_.inputs[1].default_value = 0.18; gl.new(sp.outputs[ci], d_.inputs[0]); p_ = gn.new('ShaderNodeMath'); p_.operation = 'POWER'; p_.inputs[1].default_value = CONTRAST; gl.new(d_.outputs[0], p_.inputs[0])
    m_ = gn.new('ShaderNodeMath'); m_.operation = 'MULTIPLY'; m_.inputs[1].default_value = 0.18; gl.new(p_.outputs[0], m_.inputs[0]); gl.new(m_.outputs[0], cb.inputs[ci])
gl.new(cb.outputs['Color'], go_.inputs['Colour'])
imgs = {}
def image(tid):
    if tid not in imgs: im = bpy.data.images.load(os.path.join(SRC, 'tex', '%08x.png' % tid)); im.colorspace_settings.name = 'sRGB'; im.alpha_mode = 'CHANNEL_PACKED'; imgs[tid] = im
    return imgs[tid]
combos = {}; mi = np.zeros(n, np.int32)
keys = np.stack([TEX, LMP, CUT.astype(np.int64), ONE.astype(np.int64)], 1); uq, inv = np.unique(keys, axis=0, return_inverse=True)
for k, (tid, pg, cut, one) in enumerate(uq.tolist()):
    m = bpy.data.materials.new('%08x%s%s' % (tid, '_a' if cut else '', '_lm%d' % (pg & 0xffff) if pg >= 0 else '')); m.use_nodes = True; N = m.node_tree.nodes; L = m.node_tree.links
    for x in list(N):
        if x.bl_idname != 'ShaderNodeOutputMaterial': N.remove(x)
    o = next(x for x in N if x.bl_idname == 'ShaderNodeOutputMaterial'); t = N.new('ShaderNodeTexImage'); t.image = image(tid); g = N.new('ShaderNodeGroup'); g.node_tree = grp; g.inputs['Light'].default_value = (1, 1, 1, 1); L.new(t.outputs['Color'], g.inputs['Picture'])
    if pg >= 0:
        u = N.new('ShaderNodeUVMap'); u.uv_map = 'LM'; lt = N.new('ShaderNodeTexImage'); lt.image = image(pg); lt.extension = 'EXTEND'; L.new(u.outputs['UV'], lt.inputs['Vector']); L.new(lt.outputs['Color'], g.inputs['Light'])
    e = N.new('ShaderNodeEmission'); L.new(g.outputs['Colour'], e.inputs['Color']); sh = e.outputs['Emission']
    if SHADE:                                                         # RT_SHADE=1: a plain light by the true normal on top, to READ SHAPES in a build that has no baked light yet (rounding dry runs)
        gq = N.new('ShaderNodeNewGeometry'); dq = N.new('ShaderNodeVectorMath'); dq.operation = 'DOT_PRODUCT'; dq.inputs[1].default_value = (0.35, -0.45, 0.82); L.new(gq.outputs['True Normal'], dq.inputs[0])
        aq = N.new('ShaderNodeMath'); aq.operation = 'ABSOLUTE'; L.new(dq.outputs['Value'], aq.inputs[0]); mq = N.new('ShaderNodeMath'); mq.operation = 'MULTIPLY_ADD'; mq.inputs[1].default_value = 0.75; mq.inputs[2].default_value = 0.25; L.new(aq.outputs[0], mq.inputs[0])
        xq = N.new('ShaderNodeVectorMath'); xq.operation = 'SCALE'; L.new(g.outputs['Colour'], xq.inputs[0]); L.new(mq.outputs[0], xq.inputs['Scale']); L.new(xq.outputs['Vector'], e.inputs['Color'])
    if cut:
        tr = N.new('ShaderNodeBsdfTransparent'); mx = N.new('ShaderNodeMixShader'); L.new(t.outputs['Alpha'], mx.inputs['Fac']); L.new(tr.outputs['BSDF'], mx.inputs[1]); L.new(sh, mx.inputs[2]); sh = mx.outputs['Shader']
        try: m.surface_render_method = 'DITHERED'
        except Exception: m.blend_method = 'CLIP'
    L.new(sh, o.inputs['Surface']); m.use_backface_culling = bool(one); me.materials.append(m)
me.polygons.foreach_set('material_index', inv.astype(np.int32)); me.update(); ob = bpy.data.objects.new('course as built', me); sc = bpy.context.scene; sc.collection.objects.link(ob)
# ---- sky dome (as rt_build.py: the 1995 picture, bottom row on the horizon, top row at 28.28 degrees by tan, 8 times round)
sky = bpy.data.images.load(os.path.join(_classic(), 'courses', 'src', 'course1_mountain', 'textures', 'tex_s1_x0512_y0000_256x256_c096.png')); w_, h_ = sky.size; px = np.array(sky.pixels[:], np.float32).reshape(h_, w_, -1); toprow = np.median(px[-1, :, :3], axis=0)
lin = lambda c: tuple(float(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92) for x in c)
REP = 8; TOP = math.radians(28.28); RAD = 4000.0; SEG = 96; cx, cz = [float(x) for x in D['centre'].mean(0)]; cz = -cz if False else cz
els = [0.0] + [math.atan(math.tan(TOP) * k / 6) for k in range(1, 7)]; cap = [math.radians(e) for e in (40, 55, 70, 82, 90)]; allr = [math.radians(-12)] + els + cap; V = []; F = []; FU = []; FM = []
def ring(el):
    base = len(V)
    for s in range(SEG + 1): az = 2 * math.pi * s / SEG; V.append((cx + RAD * math.cos(az) * math.cos(el), cz + RAD * math.sin(az) * math.cos(el), RAD * math.sin(el)))
    return base
uvof = lambda s, el: ((math.pi / 2 - 2 * math.pi * s / SEG) / (2 * math.pi) * REP, max(0.0, min(1.0, math.tan(max(el, 0.0)) / math.tan(TOP))) if el < 1.5 else 1.0)
bases = [ring(e) for e in allr]
for k in range(len(allr) - 1):
    e0, e1 = allr[k], allr[k + 1]; mat = 2 if e1 <= 1e-9 else (0 if e1 <= TOP + 1e-9 else 1)
    for s in range(SEG): F.append([bases[k] + s, bases[k] + s + 1, bases[k + 1] + s + 1, bases[k + 1] + s]); FM.append(mat); FU.append([uvof(s, e0), uvof(s + 1, e0), uvof(s + 1, e1), uvof(s, e1)])
dm = bpy.data.meshes.new('sky dome'); dm.from_pydata(V, [], F); dm.update(); dm.uv_layers.new(name='UVMap').data.foreach_set('uv', np.array(FU, np.float32).ravel()); dm.polygons.foreach_set('material_index', FM)
def emat(name, image_=None, colour=None):
    m = bpy.data.materials.new(name); m.use_nodes = True; N = m.node_tree.nodes; L = m.node_tree.links
    for x in list(N):
        if x.bl_idname != 'ShaderNodeOutputMaterial': N.remove(x)
    o = next(x for x in N if x.bl_idname == 'ShaderNodeOutputMaterial'); e = N.new('ShaderNodeEmission'); L.new(e.outputs['Emission'], o.inputs['Surface'])
    if image_ is not None:
        tx = N.new('ShaderNodeTexImage'); tx.image = image_; h2 = N.new('ShaderNodeHueSaturation'); h2.inputs['Saturation'].default_value = SKYSAT; h2.inputs['Value'].default_value = 0.97; L.new(tx.outputs['Color'], h2.inputs['Color']); L.new(h2.outputs['Color'], e.inputs['Color'])
    else:
        import colorsys; hh, ss, vv = colorsys.rgb_to_hsv(*lin(colour)); e.inputs['Color'].default_value = (*colorsys.hsv_to_rgb(hh, min(1.0, ss * (SKYSAT if 'above' in name else 1.0)), vv * (0.97 if 'above' in name else 1.0)), 1.0)
    m.use_backface_culling = False; return m
for m in (emat('sky picture', image_=sky), emat('sky above', colour=toprow), emat('sky below (sea colour)', colour=(25 / 255, 63 / 255, 129 / 255))): dm.materials.append(m)
sc.collection.objects.link(bpy.data.objects.new('sky dome', dm))
sc.render.engine = 'BLENDER_EEVEE'; vs = sc.view_settings; vs.view_transform = 'Standard'; vs.look = 'None'; vs.exposure = 0; vs.gamma = 1; sc.render.image_settings.file_format = 'PNG'
try: sc.eevee.taa_render_samples = int(os.environ.get('RT_SAMPLES', '16'))
except Exception: pass
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera = cam; cam.data.clip_start = 0.3; cam.data.clip_end = 20000; Wv = lambda p: Vector((p[0], -p[2], p[1]))
for v in json.load(open(VIEWS)):
    if 'ortho' in v: continue
    px_ = v.get('px', 960); sc.render.resolution_x = px_; sc.render.resolution_y = int(px_ * v.get('aspect', 0.625)); e_, t_ = Wv(v['eye']), Wv(v['target']); cam.location = e_; cam.rotation_euler = (t_ - e_).to_track_quat('-Z', 'Y').to_euler(); cam.data.lens = v.get('lens', 20)
    sc.render.filepath = os.path.join(OUT, v['name'] + '.png'); bpy.ops.render.render(write_still=True)
print('ASBUILT_SCENE triangles %d materials %d' % (n, len(me.materials)))
if SAVE:
    for im in bpy.data.images:
        if im.filepath and not im.packed_file: im.pack()
    bpy.ops.wm.save_as_mainfile(filepath=SAVE); print('ASBUILT_SCENE saved', SAVE)
