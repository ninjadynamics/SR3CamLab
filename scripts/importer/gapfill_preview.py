"""Before / after pictures of a face-list dump (import_classic, environment GAPFILL_DUMP=<file.pkl>) from the places of the
user's annotated screenshots.   python gapfill_preview.py <dump.pkl> <prefix> [slice ...]
-> work/previews/<prefix><n>.png (Blender, background). The road is the grey strip SR3 draws; the sea its sheet."""
import os, sys, pickle, subprocess
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE); WORK = os.path.dirname(HERE)
BL = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
SHOTS = [187, 269, 339, 386, 445, 573, 679]                            # road slices of SR3_20261007_0912{06,14,20,23,30,40,45}.png (estimated from the scenery)
BLPY = '''
import bpy, math, mathutils, sys, os, json
a = sys.argv[sys.argv.index('--') + 1:]; OBJ, OUT, CAMS = a[0], a[1], json.load(open(a[2]))
sc = bpy.context.scene
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
sun = bpy.data.objects.new('sun', bpy.data.lights.new('sun', 'SUN')); sun.data.energy = 2.2; sun.rotation_euler = (math.radians(40), 0, math.radians(30)); sc.collection.objects.link(sun)
w = bpy.data.worlds.new('sky'); w.use_nodes = True; w.node_tree.nodes['Background'].inputs[0].default_value = (0.31, 0.41, 0.75, 1); w.node_tree.nodes['Background'].inputs[1].default_value = 1.0; sc.world = w
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); sc.collection.objects.link(cam); sc.camera = cam; cam.data.clip_end = 5000; cam.data.clip_start = 0.3; cam.data.lens = 21
names = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties['engine'].enum_items]
sc.render.engine = 'BLENDER_EEVEE_NEXT' if 'BLENDER_EEVEE_NEXT' in names else 'BLENDER_EEVEE'
sc.render.resolution_x = 1280; sc.render.resolution_y = 720; sc.view_settings.view_transform = 'Standard'
for name, pos, tgt in CAMS:
    cam.location = pos; cam.rotation_euler = (mathutils.Vector(tgt) - mathutils.Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
    sc.render.filepath = os.path.join(OUT, name); bpy.ops.render.render(write_still=True)
print('done')
'''
def main(dump, prefix, slices=()):
    import fill1995 as F, json
    d = pickle.load(open(dump, 'rb')); rd = d['rd']; faces = d['faces'] + d['sky'] + d['extra'] + F.road_faces(rd); zs = -1.0
    tmp = os.path.join(WORK, 'tmp', 'gapfill_preview'); os.makedirs(tmp, exist_ok=True); obj = os.path.join(tmp, prefix + 'scene.obj')
    tex = [os.path.join(os.path.dirname(WORK), 'classic', 'courses', 'src', 'course1_mountain', 'textures'), os.path.join(WORK, 'tmp', 'bake_src_mountain'), os.path.join(WORK, 'classic_tex', 'course1', 'textures')]
    F._write_obj(obj, sorted(faces, key=lambda f: f[0]), rd, zs, tex)
    cen = np.asarray(rd['V'][:, rd['hw']], float); n = len(cen); cams = []
    bl = lambda p: (float(p[0] - rd['ox']), float(-(p[2] - rd['oz']) / zs), float(p[1]))                  # SR3 -> OBJ (x, y, z) -> Blender (x, -z, y)
    for k, s_ in enumerate(list(slices) or SHOTS):
        s_ = str(s_); air = {'r': 1.0, 'l': -1.0}.get(s_[-1], 0.0); foot = {'w': 1.0, 'v': -1.0}.get(s_[-1], 0.0); i = int(s_.rstrip('rlwv'))
        a = cen[(i - 9) % n] + (0, 4.3, 0); b = cen[(i + 12) % n] + (0, 0.3, 0)                              # SR3's chase camera sits about this high
        if air: a = cen[i] + (0, 55.0, 0) - rd['D'][i] * 50.0 + rd['lat'][i] * air * 70.0; b = cen[i]         # 'NNNr' / 'NNNl': from the air, right / left of the road
        if foot: a = cen[i] + rd['lat'][i] * foot * 3.5 + (0, 1.1, 0); b = cen[(i + 9) % n] + rd['lat'][(i + 9) % n] * foot * 7.5 + (0, 0.1, 0)      # 'NNNw' / 'NNNv': close to the ground, along the foot of the right / left wall
        cams.append(('%s%d.png' % (prefix, k + 1), bl(a), bl(b)))
    cj = os.path.join(tmp, prefix + 'cams.json'); json.dump(cams, open(cj, 'w')); py = os.path.join(tmp, 'bl.py'); open(py, 'w').write(BLPY)
    r = subprocess.run([BL, '-b', '--factory-startup', '--python', py, '--', obj, os.path.join(WORK, 'previews'), cj], capture_output=True, text=True, timeout=1800)
    print(prefix, 'done' if 'done' in r.stdout else ('FAILED: ' + r.stdout[-600:] + r.stderr[-600:]))
if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
