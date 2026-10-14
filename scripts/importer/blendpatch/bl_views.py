"""Blender, headless: stills of a course scene from given places, to LOOK at a generated patch before anyone else does.
    blender -b <scene.blend> --python bl_views.py -- <views.json> <out folder> [only=<name part>]
views.json: [{"name", "eye": [x, y, z], "target": [x, y, z]}] in the decoded scene's coordinates (y up). Per view three pictures:
  <name>_a.png  textured, as the scene is
  <name>_b.png  the patch faces (vertex group PATCH) in flat magenta with their edges drawn: the fill's own wireframe
  <name>_c.png  straight down from above, patch faces magenta with edges"""
import bpy, sys, json, os, bmesh
import numpy as np
from mathutils import Vector
a = sys.argv[sys.argv.index('--') + 1:]; views = json.load(open(a[0])); OUT = a[1]; only = [x[5:] for x in a[2:] if x.startswith('only=')]; passes = ''.join(x[7:] for x in a[2:] if x.startswith('passes=')) or 'abc'; os.makedirs(OUT, exist_ok=True)      # a view with "ortho": <metres across> is taken straight down, without perspective
sc = bpy.context.scene; ob = bpy.data.objects['1995 course (RAW2)']; me = ob.data
for o in bpy.data.objects:
    if o is not ob: o.hide_render = True
sc.render.engine = 'BLENDER_WORKBENCH'; sh = sc.display.shading; sh.light = 'FLAT'; sh.color_type = 'TEXTURE'; sc.render.resolution_x = 1280; sc.render.resolution_y = 720; sc.render.resolution_percentage = 100
sc.render.image_settings.file_format = 'PNG'; sc.display.render_aa = '5'
cam = bpy.data.objects.new('viewcam', bpy.data.cameras.new('viewcam')); sc.collection.objects.link(cam); sc.camera = cam; cam.data.lens = 22.0; cam.data.clip_start = 0.3; cam.data.clip_end = 6000.0
W = lambda p: Vector((p[0], -p[2], p[1]))
def shoot(name, eye, target, up='Y', ortho=None):
    cam.data.type = 'ORTHO' if ortho else 'PERSP'
    if ortho: cam.data.ortho_scale = ortho; eye = (target[0], target[1] + 400.0, target[2] + 0.01); sc.render.resolution_y = 1280
    else: sc.render.resolution_y = 720
    cam.location = W(eye); cam.rotation_euler = (W(target) - W(eye)).to_track_quat('-Z', up).to_euler(); sc.render.filepath = os.path.join(OUT, name + '.png'); bpy.ops.render.render(write_still=True)
use = [v for v in views if not only or any(o in v['name'] for o in only)]
for v in use:
    if 'a' in passes: shoot(v['name'] + '_a', v.get('eye'), v['target'], ortho=v.get('ortho'))
if passes == 'a': print('VIEWS done: %d views -> %s' % (len(use), OUT)); sys.exit(0)
# the patch faces: magenta, and a copy of them as thin black edges
g = ob.vertex_groups.get('PATCH'); gi = g.index if g else -1; inp = np.zeros(len(me.vertices), bool)
for vtx in me.vertices:
    if any(x.group == gi for x in vtx.groups): inp[vtx.index] = True
mg = bpy.data.materials.new('PATCHMARK'); mg.diffuse_color = (1.0, 0.0, 0.9, 1.0); me.materials.append(mg); mi = len(me.materials) - 1; pf = []
for pl in me.polygons:
    if all(inp[i] for i in pl.vertices): pl.material_index = mi; pf.append(pl.index)
bm = bmesh.new(); vm = {}; co = [v.co.copy() for v in me.vertices]
for fi in pf:
    vs = []
    for i in me.polygons[fi].vertices:
        k = (round(co[i].x, 3), round(co[i].y, 3), round(co[i].z, 3))
        if k not in vm: vm[k] = bm.verts.new(co[i])
        vs.append(vm[k])
    try: bm.faces.new(vs)
    except ValueError: pass
wm = bpy.data.meshes.new('patchwire'); bm.to_mesh(wm); bm.free(); wo = bpy.data.objects.new('patchwire', wm); sc.collection.objects.link(wo); wo.matrix_world = ob.matrix_world.copy(); wo.location.z += 0.03
md = wo.modifiers.new('w', 'WIREFRAME'); md.thickness = 0.12; md.use_replace = True; bk = bpy.data.materials.new('WIREBLACK'); bk.diffuse_color = (0.0, 0.0, 0.0, 1.0); wm.materials.append(bk)
print('VIEWS patch faces %d' % len(pf))
for v in use:
    if v.get('ortho'): shoot(v['name'] + '_b', None, v['target'], ortho=v['ortho']); continue
    if 'b' in passes: shoot(v['name'] + '_b', v['eye'], v['target'])
    t = v['target']
    if 'c' in passes: shoot(v['name'] + '_c', (t[0], t[1] + 90.0, t[2] + 0.01), t)
print('VIEWS done: %d views -> %s' % (len(use), OUT))
