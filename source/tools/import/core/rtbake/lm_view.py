"""Background Blender (factory): the game build's polygons with ONLY their light map on them, to look for wrong shadows.
blender -b --factory-startup --python lm_view.py -- <path of the bake> <pages .npy> <faces.pkl> <views.json> <outdir>"""
import bpy, sys, os, pickle, json
import numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]; PATH, PAGES, DUMP, VIEWS, OUT = a[:5]; os.makedirs(OUT, exist_ok=True)
D = np.load(PATH + '.lm.npz'); P = D['P'].astype(np.float64); K = np.load(PATH + '.pack.npz'); page, x0, y0, nu, nv = K['page'], K['x0'], K['y0'], K['nu'], K['nv']; pg = np.load(PAGES, mmap_mode='r'); npg = pg.shape[0]; PG = 2048
rd = pickle.load(open(DUMP, 'rb'))['rd']; ox, oz = float(rd['ox']), float(rd['oz']); G = int(np.ceil(np.sqrt(npg))); H = G * PG
atlas = np.zeros((H, H, 4), np.float32); atlas[..., 3] = 1
for p in range(npg):
    gy, gx = divmod(p, G); atlas[gy * PG:(gy + 1) * PG, gx * PG:(gx + 1) * PG, :3] = pg[p].astype(np.float32) / 255.0
img = bpy.data.images.new('lm', H, H, alpha=False); img.colorspace_settings.name = 'sRGB'; img.pixels.foreach_set(atlas[::-1].ravel()); del atlas
n = len(P); W = np.stack([P[..., 0] - ox, P[..., 2] - oz, P[..., 1]], -1).reshape(-1, 3)                 # world: course (x, y, z) -> (x, -z, y), course z = -(sr3 z - oz)
tri = np.linalg.norm(P[:, 2] - P[:, 3], axis=1) < 1e-6; faces = []                 # as the game draws them: strips [1, 0, 2, 3] = triangles (0, 1, 2) and (0, 2, 3)
for i in range(n): faces += [(4 * i, 4 * i + 1, 4 * i + 2)] if tri[i] else [(4 * i, 4 * i + 1, 4 * i + 2), (4 * i, 4 * i + 2, 4 * i + 3)]
me = bpy.data.meshes.new('lm'); me.from_pydata(W.tolist(), [], faces); me.update()
gy, gx = np.divmod(page - 1, G); X0 = gx * PG + x0; Y0 = gy * PG + y0
cu = np.stack([X0 + 0.5, X0 + nu - 0.5, X0 + nu - 0.5, X0 + 0.5], 1) / H; cv = 1 - np.stack([Y0 + 0.5, Y0 + 0.5, Y0 + nv - 0.5, Y0 + nv - 0.5], 1) / H; uv = []
for i in range(n): uv += [(cu[i, c], cv[i, c]) for c in ((0, 1, 2) if tri[i] else (0, 1, 2, 0, 2, 3))]
ul = me.uv_layers.new(name='LM'); ul.data.foreach_set('uv', np.array(uv, np.float32).ravel())
m = bpy.data.materials.new('lm'); m.use_nodes = True; N = m.node_tree.nodes; L = m.node_tree.links
for x in list(N):
    if x.bl_idname != 'ShaderNodeOutputMaterial': N.remove(x)
o = next(x for x in N if x.bl_idname == 'ShaderNodeOutputMaterial'); t = N.new('ShaderNodeTexImage'); t.image = img; t.extension = 'EXTEND'; e = N.new('ShaderNodeEmission'); L.new(t.outputs['Color'], e.inputs['Color']); L.new(e.outputs['Emission'], o.inputs['Surface']); m.use_backface_culling = False
me.materials.append(m); ob = bpy.data.objects.new('lm', me); sc = bpy.context.scene; sc.collection.objects.link(ob)
for x in list(bpy.data.objects):
    if x is not ob: bpy.data.objects.remove(x)
# the cut-out boards (trees, lamps, fences ...), see-through green, only so that one can tell what stands where
GD = pickle.load(open(DUMP, 'rb')); sv = []; sf = []
for fc in GD['faces'] + GD['sky'] + GD['extra']:
    if str(fc[0]).split('|')[0].endswith('_t') and len(fc[2]) >= 3:
        k = len(sv); sv += [(p[0] - ox, p[2] - oz, p[1]) for p in fc[2]]; sf.append(tuple(range(k, k + len(fc[2]))))
if sf and not os.environ.get('NO_BOARDS'):
    sm = bpy.data.meshes.new('boards'); sm.from_pydata(sv, [], sf); sm.update(); bmat = bpy.data.materials.new('boards'); bmat.use_nodes = True; BN = bmat.node_tree.nodes; BL = bmat.node_tree.links
    for x in list(BN):
        if x.bl_idname != 'ShaderNodeOutputMaterial': BN.remove(x)
    bo = next(x for x in BN if x.bl_idname == 'ShaderNodeOutputMaterial'); be = BN.new('ShaderNodeEmission'); be.inputs['Color'].default_value = (0.05, 0.45, 0.08, 1); bt = BN.new('ShaderNodeBsdfTransparent'); bx = BN.new('ShaderNodeMixShader'); bx.inputs['Fac'].default_value = 0.3
    BL.new(bt.outputs['BSDF'], bx.inputs[1]); BL.new(be.outputs['Emission'], bx.inputs[2]); BL.new(bx.outputs['Shader'], bo.inputs['Surface']); bmat.use_backface_culling = False
    try: bmat.surface_render_method = 'BLENDED'
    except Exception: bmat.blend_method = 'BLEND'
    sm.materials.append(bmat); sc.collection.objects.link(bpy.data.objects.new('boards', sm))
sc.render.engine = 'BLENDER_EEVEE'; sc.view_settings.view_transform = 'Standard'; sc.view_settings.look = 'None'; sc.render.image_settings.file_format = 'PNG'
if sc.world is None: sc.world = bpy.data.worlds.new('w')
sc.world.use_nodes = False; sc.world.color = (0.05, 0.1, 0.3)
cam = bpy.data.objects.new('c', bpy.data.cameras.new('c')); sc.collection.objects.link(cam); sc.camera = cam; cam.data.clip_start = 0.3; cam.data.clip_end = 5000
Wv = lambda p: Vector((p[0], -p[2], p[1]))
for v in json.load(open(VIEWS)):
    if 'ortho' in v:                                                 # top view: {"name", "ortho": [x0, x1, z0, z1] in course coordinates, "px": width}
        x0_, x1_, z0_, z1_ = v['ortho']; cam.data.type = 'ORTHO'; cam.data.ortho_scale = max(x1_ - x0_, z1_ - z0_); cam.location = ((x0_ + x1_) / 2, -(z0_ + z1_) / 2, 800.0); cam.rotation_euler = (0, 0, 0)
        sc.render.resolution_x = v.get('px', 2000); sc.render.resolution_y = int(v.get('px', 2000) * (z1_ - z0_) / (x1_ - x0_)); cam.data.clip_end = 2000; sc.render.filepath = os.path.join(OUT, v['name'] + '.png'); bpy.ops.render.render(write_still=True); continue
    cam.data.type = 'PERSP'; sc.render.resolution_x = v.get('px', 800); sc.render.resolution_y = int(v.get('px', 800) * 0.625)
    e_, t_ = Wv(v['eye']), Wv(v['target']); cam.location = e_; cam.rotation_euler = (t_ - e_).to_track_quat('-Z', 'Y').to_euler(); cam.data.lens = v.get('lens', 20); sc.render.filepath = os.path.join(OUT, v['name'] + '.png'); bpy.ops.render.render(write_still=True)
print('LMVIEW done')
