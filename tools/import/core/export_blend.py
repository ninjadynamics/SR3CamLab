"""A .blend of one step of the import stack (stack.py --blend), in the axes of the course's own OBJ export (x, y, -gameZ: the
axes of the Blender patch files).   python export_blend.py <what> <game> <course> <build name> <stack folder> <out.blend>
    rom     the course as the ROM gives it (the importer's export, the sky and the gates)
    patch   after the course's patch chain, before the rounding (the importer's ROUND_IN dump; without rounding, the round dump)
    round   after the rounding: the polygons the light is baked on (GAPFILL_DUMP)
    rt      the built track read back from its own files with its light maps (rtbake/asbuilt_decode.py + asbuilt_scene.py)
    build   the built track read back from its own files, pictures only (preview_obj.py + blendpatch/bl_build_to_blend.py)
Blender comes from the settings; it runs in the background with factory settings and packs every picture into the file."""
import os, sys, json, pickle, subprocess
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from common import *

def blender(script, *args):
    r = subprocess.run([BLENDER, '-b', '--factory-startup', '--python', os.path.join(HERE, script), '--'] + [str(a) for a in args], capture_output=True, text=True)
    print(r.stdout[-2000:], r.stderr[-1000:])
    if r.returncode: raise SystemExit('Blender failed on %s' % script)

def faces_obj(faces, baked, out_dir, base, log=print):
    """importer faces (material, object, corners, uv) -> <out_dir>/<base>.obj + .mtl + textures/*.png"""
    import build_classic as BC
    from PIL import Image
    xf = json.load(open(BC.XFORM)); ox, oz = xf['ox'], xf['oz']; BC.BAKED.update(baked)
    os.makedirs(os.path.join(out_dir, 'textures'), exist_ok=True); mats = {}
    def mat(m):
        if m in mats: return mats[m]
        nm = 'm%04d_%s' % (len(mats), str(m).replace('|', '__')[:60]); mats[m] = nm
        try: px = BC.tile_pixels(str(m))                               # ROM tiles, the course's PNGs, and the composed tiles (BC.BAKED, from the dump)
        except Exception: px = None
        if px is not None:
            rgb, hole = px[0], px[1] if len(px) > 1 else None
            a = np.dstack([rgb, np.where(hole, 0, 255).astype(np.uint8)]) if hole is not None else rgb
            Image.fromarray(np.ascontiguousarray(a).astype(np.uint8)).save(os.path.join(out_dir, 'textures', nm + '.png'))
        return nm
    with open(os.path.join(out_dir, base + '.obj'), 'w', newline='\n') as fo:
        fo.write('# %d faces from the import stack, axes of the course OBJ (x - ox, y, oz - z)\nmtllib %s.mtl\n' % (len(faces), base))
        cur_o = cur_m = None; nv = nt = 0
        for fc in faces:
            m, o, P, U = fc[0], fc[1], fc[2], fc[3]
            if o != cur_o: fo.write('o %s\n' % str(o).replace(' ', '_')); cur_o = o
            nm = mat(m)
            if nm != cur_m: fo.write('usemtl %s\n' % nm); cur_m = nm
            for p in P: fo.write('v %.4f %.4f %.4f\n' % (p[0] - ox, p[1], oz - p[2]))
            for u in U: fo.write('vt %.5f %.5f\n' % (u[0], 1.0 - u[1]))
            fo.write('f ' + ' '.join('%d/%d' % (nv + k + 1, nt + k + 1) for k in range(len(P))) + '\n'); nv += len(P); nt += len(U)
    with open(os.path.join(out_dir, base + '.mtl'), 'w', newline='\n') as fm:
        for m, nm in mats.items():
            fm.write('newmtl %s\nKd 1 1 1\n' % nm)
            if os.path.exists(os.path.join(out_dir, 'textures', nm + '.png')): fm.write('map_Kd textures/%s.png\n' % nm)
    log('%s: %d faces, %d materials' % (base, len(faces), len(mats)))
    return os.path.join(out_dir, base + '.obj')

def main(what, game, crs, name, G, out):
    import course, build_classic as BC
    cfg = course.use(game, crs); work = os.path.join(os.path.dirname(out), what); os.makedirs(work, exist_ok=True)
    cdir = os.path.join(CLASSIC, 'courses', game, cfg.get('gameplay', ''))
    BC.EXTRA_TEX = os.path.join(cdir, 'textures') if game == 'src' else os.path.join(__import__('export_adapter').folder(cfg), 'textures')
    if what == 'rom':
        objs = [BC.HI] + [os.path.join(cdir, 'src_course%s_%s.obj' % (crs, k)) for k in ('sky', 'gates')]
        blender('blendpatch/bl_obj_to_blend.py', out, *[o for o in objs if os.path.exists(o)])
    elif what in ('patch', 'round'):
        p = os.path.join(G, 'patched.pkl') if what == 'patch' and os.path.exists(os.path.join(G, 'patched.pkl')) else os.path.join(G, 'faces.pkl')
        D = pickle.load(open(p, 'rb')); faces = D['faces'] + D.get('sky', []) + D.get('extra', [])
        baked = D.get('baked') or pickle.load(open(os.path.join(G, 'faces.pkl'), 'rb')).get('baked', {})     # the patch dump has no composed tiles: the same run's round dump has them
        blender('blendpatch/bl_obj_to_blend.py', out, faces_obj(faces, baked, work, '%s_%s' % (name, what)))
    elif what == 'rt':
        r = subprocess.run([sys.executable, os.path.join(HERE, 'rtbake', 'asbuilt_decode.py'), name, os.path.join(G, 'faces.pkl'), work], cwd=HERE)
        if r.returncode: raise SystemExit('asbuilt_decode failed')
        vj = os.path.join(work, 'views.json'); json.dump([], open(vj, 'w'))
        blender('rtbake/asbuilt_scene.py', work, vj, os.path.join(work, 'shots'), out)
    elif what == 'build':
        import preview_obj; obj = preview_obj.main(name)
        blender('blendpatch/bl_build_to_blend.py', obj, out)
    else: raise SystemExit('unknown export %r' % what)
    print('saved', out)

if __name__ == '__main__':
    if len(sys.argv) < 7: print(__doc__); sys.exit(1)
    main(*sys.argv[1:7])
