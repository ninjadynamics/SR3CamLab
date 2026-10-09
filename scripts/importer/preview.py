"""Preview pictures in ..\\previews: the classic course and the SR3 track DECODED BACK from the built files.
    python preview.py [step folder name]      (default step17_classic_scenery_textured_desert4)
Top-downs with matplotlib; perspective views through the Blender MCP socket (localhost:9876) if it answers."""
import os, sys, json, socket, struct, collections
import numpy as np
import matplotlib; matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection, LineCollection
from common import *
import sbfw, trackdeform as TDm, bsp, meshgen, scene11
import build_testtrack as BT

PV = os.path.join(WORK, 'previews'); os.makedirs(PV, exist_ok=True)
CL = os.path.join(os.path.dirname(WORK), 'classic', 'obj')
CT = os.path.join(WORK, 'classic_tex', 'course1')

def decode_step(step, slot='Desert4'):
    folder = os.path.join(OUT, step, slot); tf = track_files(folder)
    f = sbfw.read_sbf(tf['master_gfx_xdata']); fx = sbfw.read_sbf(tf['master_xdata']); by = f.byid(); r = f.chunks[-1]
    td = TDm.parse_td(by[r.u32(0xc)]); n = td.n
    road = [td.verts[i]['pos'].astype(float) for i in range(1, n + 1)]
    surf = [td.verts[i]['surf'][:, 1].copy() for i in range(1, n + 1)]
    walls = []
    if r.u32(0x34) and r.u32(0x34) in by:
        b = bsp.parse_bsp(by[r.u32(0x34)]); walls = [p['v'][:3].astype(float) for p in b.poly if abs(p['pl'][1]) < 0.5]
    s = scene11.parse11(by[r.u32(4)]); meshes = []
    for mid in s.nodes[0].meshes:
        m = meshgen.parse_mesh(by[mid]); V = m['verts']; I = m['idx']; tris = []
        for k in range(len(I) - 2):
            a, b_, c = int(I[k]), int(I[k + 1]), int(I[k + 2])
            if len({a, b_, c}) == 3: tris.append((a, b_, c) if k % 2 == 0 else (b_, a, c))
        meshes.append((V['p'][:, :3].astype(float), np.array(tris), m['groups'][0][4]))
    root = fx.chunks[-1]; start, dirn = struct.unpack_from('<ii', root.data, 0x2c)
    return dict(road=road, surf=surf, walls=walls, meshes=meshes, start=start, dir=dirn, n=n, td=td)

def load_classic():
    xf = json.load(open(os.path.join(TMP, 'classic_xform.json'))); V = []; VT = []; faces = []; mat = None
    for ln in open(os.path.join(CL, 'src_course1_hi.obj')):
        if ln.startswith('v '): x, y, z = map(float, ln.split()[1:4]); V.append((x + xf['ox'], y, -z + xf['oz']))
        elif ln.startswith('vt '): VT.append(tuple(map(float, ln.split()[1:3])))
        elif ln.startswith('usemtl'): mat = ln.split()[1]
        elif ln.startswith('f '):
            ix = [tuple(int(a) - 1 for a in t.split('/')[:2]) for t in ln.split()[1:]]; faces.append((mat, [a for a, b in ix], [b for a, b in ix]))
    return np.array(V), np.array(VT), faces

def top(ax, V, faces, color, alpha=1.0, lw=0.1):
    polys = [V[f[1]][:, [0, 2]] for f in faces]
    ax.add_collection(PolyCollection(polys, facecolors=color, edgecolors=(0, 0, 0, 0.25), linewidths=lw, alpha=alpha))

def draw_sr3(ax, D, step=1, labels=True):
    road = D['road']; n = D['n']; quads = []; cols = []
    for i in range(0, n, step):
        a = road[i]; b = road[(i + step) % n]; m = min(len(a), len(b))
        for k in range(m - 1):
            quads.append([a[k][[0, 2]], a[k + 1][[0, 2]], b[k + 1][[0, 2]], b[k][[0, 2]]])
            cols.append((0.85, 0.1, 0.1, 0.55) if D['surf'][i][k] == 1 else (0.95, 0.6, 0.1, 0.6))
    ax.add_collection(PolyCollection(quads, facecolors=cols, edgecolors='none'))
    if D['walls']:
        segs = []
        for t in D['walls']:
            p = t[:, [0, 2]]; segs.append([p[0], p[2]])
        ax.add_collection(LineCollection(segs, colors=(0, 0.2, 1, 0.9), linewidths=0.8))

def figure(name, V, faces, D, centre=None, half=None, title='', overlay=True, marks=()):
    fig, ax = plt.subplots(figsize=(11, 11), dpi=130)
    top(ax, V, faces, (0.75, 0.78, 0.75), 1.0)
    if overlay and D: draw_sr3(ax, D)
    if D:
        cen = np.array([r[len(r) // 2] for r in D['road']])
        for i, lab in marks:
            ax.plot(cen[i - 1, 0], cen[i - 1, 2], 'k*', ms=12); ax.annotate(lab, (cen[i - 1, 0], cen[i - 1, 2]), textcoords='offset points', xytext=(8, 8), fontsize=10, color='k', bbox=dict(fc='w', alpha=0.8, lw=0))
        if half and half < 150:
            for i in range(0, D['n'], 10):
                if abs(cen[i, 0] - centre[0]) < half and abs(cen[i, 2] - centre[1]) < half: ax.annotate(str(i + 1), (cen[i, 0], cen[i, 2]), fontsize=6, color=(0.3, 0, 0))
    if centre is None:
        ax.set_xlim(V[:, 0].min() - 20, V[:, 0].max() + 20); ax.set_ylim(V[:, 2].min() - 20, V[:, 2].max() + 20)
    else:
        ax.set_xlim(centre[0] - half, centre[0] + half); ax.set_ylim(centre[1] - half, centre[1] + half)
    ax.set_aspect('equal'); ax.grid(alpha=0.3); ax.set_xlabel('x (m)'); ax.set_ylabel('z (m)   [SR3 / original game axes, seen from above]')
    ax.set_title(title, fontsize=11)
    p = os.path.join(PV, name); fig.savefig(p, bbox_inches='tight'); plt.close(fig); return p

def profile(name, D):
    cen = np.array([r[len(r) // 2] for r in D['road']]); n = D['n']
    fig, ax = plt.subplots(2, 1, figsize=(12, 6), dpi=120, sharex=True)
    ax[0].plot(np.arange(1, n + 1), cen[:, 1], 'r'); ax[0].set_ylabel('road centre height (m)'); ax[0].grid(alpha=0.3)
    w = [np.linalg.norm(r[-1] - r[0]) for r in D['road']]; ax[1].plot(np.arange(1, n + 1), w, 'b'); ax[1].set_ylabel('road width (m)'); ax[1].set_xlabel('slice (= metres from slice 1)'); ax[1].grid(alpha=0.3)
    ax[0].set_title('SR3 road decoded from the built files: elevation and width')
    p = os.path.join(PV, name); fig.savefig(p, bbox_inches='tight'); plt.close(fig); return p

# ---------------------------------------------------------------- Blender
def blender(code, timeout=600):
    s = socket.create_connection(('127.0.0.1', 9876), timeout=5); s.settimeout(timeout)
    s.sendall(json.dumps({"type": "execute_code", "params": {"code": code}}).encode())
    buf = b''
    while True:
        try: ch = s.recv(65536)
        except socket.timeout: break
        if not ch: break
        buf += ch
        try: json.loads(buf.decode()); break
        except Exception: continue
    s.close(); return buf.decode(errors='replace')[:400]

def to_bl(P): return np.stack([P[:, 0], P[:, 2], P[:, 1]], 1)       # SR3 (LH, Y up) -> Blender (RH, Z up)

def export_npz(D, V, VT, faces):
    """arrays for the Blender side"""
    # classic, textured
    mats = sorted({f[0] for f in faces}); mi = {m: k for k, m in enumerate(mats)}
    loops = []; lv = []; uv = []; fm = []
    for mat, vi, ti in faces:
        fm.append(mi[mat]); loops.append(len(vi)); lv += vi[::-1]; uv += [tuple(VT[t]) for t in ti[::-1]]
    np.savez(os.path.join(TMP, 'pv_classic.npz'), verts=to_bl(V), loops=np.array(loops), lv=np.array(lv), uv=np.array(uv), fm=np.array(fm))
    json.dump([os.path.join(CT, 'textures', m + '.png') if m.startswith('tex_') else None for m in mats], open(os.path.join(TMP, 'pv_classic_mats.json'), 'w'))
    # SR3 decoded: road (2 colours), walls, scenery
    rv = []; rf = []; rc = []
    road = D['road']; n = D['n']; base = []
    for i in range(n): base.append(len(rv)); rv += list(road[i])
    for i in range(n):
        j = (i + 1) % n; m = min(len(road[i]), len(road[j]))
        for k in range(m - 1):
            rf.append((base[i] + k, base[j] + k, base[j] + k + 1, base[i] + k + 1)); rc.append(0 if D['surf'][i][k] == 1 else 1)
    wv = []; wf = []
    for t in D['walls']: wf.append((len(wv), len(wv) + 1, len(wv) + 2)); wv += list(t)
    sv = []; sf = []
    for P, T, mid in D['meshes']:
        o = len(sv); sv += list(P); sf += [(a + o, b + o, c + o) for a, b, c in T]
    np.savez(os.path.join(TMP, 'pv_sr3.npz'), rv=to_bl(np.array(rv)), rf=np.array(rf), rc=np.array(rc), wv=to_bl(np.array(wv)) if wv else np.zeros((0, 3)), wf=np.array(wf),
             sv=to_bl(np.array(sv)) if sv else np.zeros((0, 3)), sf=np.array(sf))

BL = r'''
import bpy, numpy as np, json, math, os
from mathutils import Vector
TMP = r"%(tmp)s"; PV = r"%(pv)s"
def scene(name):
    if name in bpy.data.scenes: bpy.data.scenes.remove(bpy.data.scenes[name])
    sc = bpy.data.scenes.new(name)
    w = bpy.data.worlds.new(name + "_world"); w.color = (0.55, 0.68, 0.85); sc.world = w
    sc.render.engine = 'BLENDER_WORKBENCH'; sc.display.shading.light = 'STUDIO'; sc.display.shading.color_type = 'TEXTURE'
    sc.display.shading.show_backface_culling = False; sc.display.shading.show_shadows = False
    sc.render.resolution_x = 1600; sc.render.resolution_y = 1000; sc.render.film_transparent = False
    return sc
def mesh(sc, name, verts, faces, color=None):
    me = bpy.data.meshes.new(name); me.from_pydata([tuple(v) for v in verts], [], [tuple(int(i) for i in f) for f in faces]); me.update()
    ob = bpy.data.objects.new(name, me); sc.collection.objects.link(ob)
    if color is not None:
        m = bpy.data.materials.new(name + "_m"); m.diffuse_color = color; me.materials.append(m)
    return ob
def cam(sc, name, loc, target, ortho=None, lens=28):
    cd = bpy.data.cameras.new(name); ob = bpy.data.objects.new(name, cd); sc.collection.objects.link(ob)
    ob.location = loc; d = Vector(target) - Vector(loc); ob.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    cd.clip_end = 5000; cd.lens = lens
    if ortho: cd.type = 'ORTHO'; cd.ortho_scale = ortho
    return ob
def shot(sc, c, path):
    sc.camera = c; sc.render.filepath = path; bpy.ops.render.render(write_still=True, scene=sc.name)
def classic(sc):
    d = np.load(os.path.join(TMP, "pv_classic.npz")); mats = json.load(open(os.path.join(TMP, "pv_classic_mats.json")))
    me = bpy.data.meshes.new("classic"); loops = d["loops"]; lv = d["lv"]
    me.vertices.add(len(d["verts"])); me.vertices.foreach_set("co", d["verts"].astype(np.float32).ravel())
    me.loops.add(len(lv)); me.loops.foreach_set("vertex_index", lv.astype(np.int32))
    me.polygons.add(len(loops)); st = np.concatenate([[0], np.cumsum(loops)[:-1]]).astype(np.int32)
    me.polygons.foreach_set("loop_start", st); me.polygons.foreach_set("loop_total", loops.astype(np.int32))
    uvl = me.uv_layers.new(name="uv"); uvl.data.foreach_set("uv", d["uv"].astype(np.float32).ravel())
    for k, p in enumerate(mats):
        m = bpy.data.materials.new("cl_%%d" %% k); m.use_nodes = True; m.diffuse_color = (0.6, 0.6, 0.6, 1)
        if p and os.path.exists(p):
            nt = m.node_tree; tx = nt.nodes.new("ShaderNodeTexImage"); tx.image = bpy.data.images.load(p, check_existing=True); tx.interpolation = 'Closest'
            b = nt.nodes.get("Principled BSDF"); nt.links.new(tx.outputs["Color"], b.inputs["Base Color"]); nt.nodes.active = tx
        me.materials.append(m)
    me.polygons.foreach_set("material_index", d["fm"].astype(np.int32)); me.update(); me.validate()
    ob = bpy.data.objects.new("classic", me); sc.collection.objects.link(ob); return ob
def sr3(sc, scenery=True):
    d = np.load(os.path.join(TMP, "pv_sr3.npz"))
    rf = d["rf"]; rc = d["rc"]
    mesh(sc, "road_tarmac", d["rv"], rf[rc == 0], (0.25, 0.25, 0.28, 1)); mesh(sc, "road_gravel", d["rv"], rf[rc == 1], (0.75, 0.5, 0.2, 1))
    if len(d["wf"]):
        w = mesh(sc, "walls", d["wv"], d["wf"], (0.1, 0.3, 1.0, 1)); w.display_type = 'WIRE'
    if scenery and len(d["sf"]): mesh(sc, "scenery", d["sv"], d["sf"], (0.8, 0.8, 0.75, 1))
views = json.load(open(os.path.join(TMP, "pv_views.json")))
done = []
sc = scene("SR3KB_classic"); classic(sc)
for v in views:
    c = cam(sc, v["name"], v["loc"], v["tgt"], v.get("ortho")); shot(sc, c, os.path.join(PV, "classic_" + v["name"] + ".png")); done.append(v["name"])
sc2 = scene("SR3KB_sr3"); sc2.display.shading.color_type = 'MATERIAL'; sr3(sc2)
for v in views:
    c = cam(sc2, v["name"] + "_b", v["loc"], v["tgt"], v.get("ortho")); shot(sc2, c, os.path.join(PV, "sr3_" + v["name"] + ".png"))
sc3 = scene("SR3KB_overlay"); sc3.display.shading.color_type = 'MATERIAL'; o = classic(sc3); sr3(sc3, scenery=False)
for ob in sc3.objects:
    if ob.name.startswith("road"): ob.location.z += 0.15
for v in views:
    c = cam(sc3, v["name"] + "_c", v["loc"], v["tgt"], v.get("ortho")); shot(sc3, c, os.path.join(PV, "overlay_" + v["name"] + ".png"))
for n_ in ("SR3KB_classic", "SR3KB_sr3", "SR3KB_overlay"): bpy.data.scenes.remove(bpy.data.scenes[n_])
'''

def main(step='step17_classic_scenery_textured_desert4'):
    D = decode_step(step); V, VT, faces = load_classic(); out = []
    cen = np.array([r[len(r) // 2] for r in D['road']]); n = D['n']
    d = np.roll(cen, -1, 0) - cen; d[:, 1] = 0; d /= np.linalg.norm(d, axis=1)[:, None]
    turn = np.arccos(np.clip((d * np.roll(d, -1, 0)).sum(1), -1, 1)); it = int(np.convolve(np.concatenate([turn[-10:], turn, turn[:10]]), np.ones(21), 'valid').argmax()) + 1
    g = np.abs(np.roll(cen[:, 1], -20) - cen[:, 1]); ig = int(g.argmax()) + 10
    st = D['start']
    marks = [(st, 'start line (slice %d, direction %+d)' % (st, D['dir'])), (it, 'tightest bend (slice %d)' % it), (ig, 'steepest (slice %d)' % ig)]
    out.append(figure('classic_course1_top.png', V, faces, None, title='SEGA Rally Championship course 1 = MOUNTAIN, visual model, original game axes (not mirrored)', overlay=False))
    out.append(figure('overlay_top.png', V, faces, D, title='%s decoded from the built files over the classic model\nred = SR3 road cells (tarmac), orange = gravel cells, blue = wall polygons' % step, marks=marks))
    for nm, i in (('start', st), ('tightest_bend', it), ('steepest', ig)):
        out.append(figure('overlay_closeup_%s.png' % nm, V, faces, D, centre=(cen[i - 1, 0], cen[i - 1, 2]), half=70, title='%s: close-up %s, slice numbers along the centre' % (step, nm), marks=marks))
    out.append(profile('sr3_road_profile.png', D))
    # perspective views with Blender
    export_npz(D, V, VT, faces)
    def view(name, i, back=60, up=25, side=0):
        c = cen[i - 1]; dd = d[i - 1]; lat = np.array([dd[2], 0, -dd[0]]); loc = c - dd * back + lat * side + np.array([0, up, 0]); tgt = c + dd * 30
        return dict(name=name, loc=[float(loc[0]), float(loc[2]), float(loc[1])], tgt=[float(tgt[0]), float(tgt[2]), float(tgt[1])])
    mid = cen.mean(0)
    views = [dict(name='persp_overview', loc=[float(mid[0] - 700), float(mid[2] - 800), 650.0], tgt=[float(mid[0]), float(mid[2]), 30.0]),
             view('persp_start', st), view('persp_tightest_bend', it, back=70, up=40), view('persp_steepest', ig, back=70, up=20, side=25), view('driver_start', st, back=6, up=2.2)]
    json.dump(views, open(os.path.join(TMP, 'pv_views.json'), 'w'))
    try:
        res = blender(BL % dict(tmp=TMP, pv=PV)); print('blender:', res)
        for v in views:
            for pre in ('classic_', 'sr3_', 'overlay_'):
                p = os.path.join(PV, pre + v['name'] + '.png')
                if os.path.exists(p): out.append(p)
    except Exception as e:
        print('blender not used:', e)
    print('\n'.join(out)); return out, marks

if __name__ == '__main__':
    main(*sys.argv[1:2])
