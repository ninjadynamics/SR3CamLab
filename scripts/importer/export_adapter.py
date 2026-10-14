"""Course exports made by other tools (scripts/rom_tools: Daytona USA) -> the importer's own input files, so that the rest
of the importer reads such a course the way it reads a SEGA Rally Championship course (classic_export.py, m2_collision.py).

    prepare(cfg)  writes  <WORK>/classic_tex/<game>_course<N>/
        <visual>               the course OBJ (axes x, y, -gameZ, as SRC's), every face WITH texture coordinates: the
                               export writes the faces of flat-colour materials (col_...) without any; they get a plain
                               mapping in their own plane (1 repeat per 64 m: their picture is one colour, so only the
                               importer's uv checks see it)
        <visual>.mtl           the export's materials, plus a picture for every flat-colour material (for renders)
        <centreline>           the export's centre line in the OBJ's axes (Z negated) when the export wrote it in game axes
        textures/              the export's tiles, plus one 8 x 8 picture per flat-colour material in its colour
                               (materials.json "rgb", the colour space of the tiles)
The collision OBJ is read where it is (already in the OBJ's axes; without 'o attr_' groups every polygon has attribute 0).

Course settings (courses/<game>_<N>.json):
    "export":          folder under classic/, e.g. "courses/daytona/beginner"
    "visual", "collision", "centreline": file names in that folder
    "centreline_axes": "game" when the export's centre line (and its driving lines) are in game axes
Nothing here touches the export itself."""
import os, json, shutil
import numpy as np
from common import *

def folder(cfg):
    """the importer's copy of a course export"""
    return os.path.join(WORK, 'classic_tex', '%s_course%s' % (cfg['game'], cfg['course']))

def source(cfg):
    """the export folder the other tool wrote"""
    return os.path.join(os.path.dirname(WORK), 'classic', *str(cfg['export']).replace('\\', '/').split('/'))

def flat_uv(P, per_m=1.0 / 64):
    """texture coordinates of a face in its own plane (min 0, 0)"""
    P = np.asarray(P, float); n = np.zeros(3)
    for i in range(len(P)): n += np.cross(P[i], P[(i + 1) % len(P)])
    ln = np.linalg.norm(n)
    if ln < 1e-12: return [(0.0, 0.0)] * len(P)
    n /= ln; up = np.array([0.0, 1.0, 0.0]) if abs(n[1]) < 0.9 else np.array([0.0, 0.0, 1.0])
    e1 = np.cross(up, n); e1 /= np.linalg.norm(e1); e2 = np.cross(n, e1); d = P - P[0]; U = np.stack([d @ e1, d @ e2], 1) * per_m
    U -= U.min(0); return [tuple(map(float, u)) for u in U]

def prepare(cfg, force=False, log=print):
    from PIL import Image
    src = source(cfg); out = folder(cfg); os.makedirs(os.path.join(out, 'textures'), exist_ok=True)
    vis_in = os.path.join(src, cfg['visual']); vis_out = os.path.join(out, cfg['visual']); mtl_out = vis_out[:-4] + '.mtl'
    mats = json.load(open(os.path.join(src, 'materials.json'))) if os.path.exists(os.path.join(src, 'materials.json')) else {}
    # tiles: the export's, then one picture per flat-colour material
    nt = 0
    for fn in sorted(os.listdir(os.path.join(src, 'textures'))):
        a, b = os.path.join(src, 'textures', fn), os.path.join(out, 'textures', fn)
        if force or not os.path.exists(b) or os.path.getmtime(b) < os.path.getmtime(a): shutil.copy2(a, b); nt += 1
    flat = {k: v for k, v in mats.items() if k.startswith('col_') and v.get('rgb') is not None}
    for k, v in sorted(flat.items()):
        p = os.path.join(out, 'textures', k + '.png'); rgb = np.clip(np.round(np.asarray(v['rgb'], float) * 255.0), 0, 255).astype(np.uint8)
        im = np.zeros((8, 8, 4), np.uint8); im[:, :, :3] = rgb; im[:, :, 3] = 255
        if force or not os.path.exists(p) or not np.array_equal(np.asarray(Image.open(p).convert('RGBA')), im): Image.fromarray(im, 'RGBA').save(p)
    # the course OBJ, every face with texture coordinates
    V = []; Vl = []; VT = []; head = []; body = []; faces = []; nfix = 0       # (all v, then all vt, then the objects: the original indices stay valid and the added vt come last)
    for ln in open(vis_in):
        if ln.startswith('v '): V.append(tuple(map(float, ln.split()[1:4]))); Vl.append(ln)
        elif ln.startswith('vt '): VT.append(ln)
        elif ln.startswith('mtllib'): head.append('mtllib %s\n' % os.path.basename(mtl_out))
        elif ln.startswith('#') and not body: head.append(ln)
        else: body.append(ln)
    for k, ln in enumerate(body):
        if not ln.startswith('f '): continue
        tok = ln.split()[1:]
        if all('/' in t and t.split('/')[1] for t in tok): continue
        vi = [int(t.split('/')[0]) for t in tok]; uv = flat_uv([V[i - 1] for i in vi]); k0 = len(VT) + 1
        VT += ['vt %.6f %.6f\n' % u for u in uv]; body[k] = 'f ' + ' '.join('%d/%d' % (v, k0 + j) for j, v in enumerate(vi)) + '\n'; nfix += 1
    txt = ''.join(head + Vl + VT + body)
    if force or not os.path.exists(vis_out) or open(vis_out).read() != txt: open(vis_out, 'w').write(txt)
    mtl = open(vis_in[:-4] + '.mtl').read().split('newmtl ')
    def mat_block(b):
        name = b.split('\n', 1)[0].strip()
        if name in flat: return 'newmtl %s\nKd 1 1 1\nKs 0 0 0\nmap_Kd textures/%s.png\n\n' % (name, name)
        return 'newmtl ' + b
    mt = mtl[0] + ''.join(mat_block(b) for b in mtl[1:])
    if force or not os.path.exists(mtl_out) or open(mtl_out).read() != mt: open(mtl_out, 'w').write(mt)
    # centre line in the OBJ's axes
    cl_in = os.path.join(src, cfg['centreline']); cl_out = os.path.join(out, cfg['centreline'])
    C = np.loadtxt(cl_in, delimiter=',', comments='#')
    if cfg.get('centreline_axes', 'obj') == 'game': C = C[:, :3] * np.array([1.0, 1.0, -1.0])
    ct = '# x,y,z centre line of %s (Z negated like the OBJ; written by export_adapter.py)\n' % os.path.relpath(cl_in, os.path.dirname(WORK)) + ''.join('%.4f,%.4f,%.4f\n' % tuple(p[:3]) for p in C)
    if force or not os.path.exists(cl_out) or open(cl_out).read() != ct: open(cl_out, 'w').write(ct)
    log('       export (%s): %s ; %d tiles copied, %d flat-colour pictures, %d faces given texture coordinates in their plane, centre line %d points (%s axes)' %
        (cfg['game'], os.path.relpath(src, os.path.dirname(WORK)), nt, len(flat), nfix, len(C), cfg.get('centreline_axes', 'obj')))
    return dict(visual=vis_out, centreline=cl_out, collision=os.path.join(src, cfg['collision']), textures=os.path.join(out, 'textures'))

def line_files(cfg):
    """the driving lines named by the course setting ai_lines, as arrays (n, 3) in GAME axes"""
    out = []
    for fn in cfg.get('ai_lines', ()):
        A = np.loadtxt(os.path.join(source(cfg), fn), delimiter=',', comments='#')[:, :3]
        if cfg.get('centreline_axes', 'obj') != 'game': A = A * np.array([1.0, 1.0, -1.0])
        out.append(A)
    return out
