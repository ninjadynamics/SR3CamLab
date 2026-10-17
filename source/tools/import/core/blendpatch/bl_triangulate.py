"""Blender, headless: every face of more than three corners becomes triangles, with no triangle of no area.
    blender -b <scene.blend> --python bl_triangulate.py -- <out.blend>
A corner lying on a straight stretch of its face's outline is dropped when no other face uses it (it carries nothing); one that other
faces do use stays, and the triangles are turned so that none lies flat on that stretch (the corner stays shared: no T-junction)."""
import bpy, bmesh, sys, collections
OUT = sys.argv[sys.argv.index('--') + 1]; o = bpy.data.objects['1995 course (RAW2)']; me = o.data
bm = bmesh.new(); bm.from_mesh(me); bm.normal_update(); ng = [f for f in bm.faces if len(f.verts) > 3]; n0 = len(bm.faces); sizes = collections.Counter(len(f.verts) for f in ng)
area0 = sum(f.calc_area() for f in ng); cen = [[round(c, 1) for c in f.calc_center_median()] for f in ng]
# corners on a straight stretch that nothing else uses
drop = []
for f in ng:
    L = list(f.loops)
    for l in L:
        a, b, c = l.link_loop_prev.vert, l.vert, l.link_loop_next.vert; d = (c.co - a.co)
        if d.length < 1e-6: continue
        if (b.co - a.co).cross(d).length / d.length < 0.0005 and 0 < (b.co - a.co).dot(d) < d.length_squared and all(g is f for g in b.link_faces): drop.append(b)
drop = list(dict.fromkeys(drop)); nd = len(drop)
if drop: bmesh.ops.dissolve_verts(bm, verts=drop)
ng = [f for f in bm.faces if len(f.verts) > 3]
r = bmesh.ops.triangulate(bm, faces=ng, quad_method='BEAUTY', ngon_method='BEAUTY'); tris = set(r['faces']); bm.normal_update()
# a triangle lying flat on a straight stretch: its long edge is turned (the two triangles on it swap their diagonal), or, on an open rim, it goes
turned = gone = 0
for _ in range(8):
    flat = [f for f in tris if f.is_valid and f.calc_area() < 1e-7]
    if not flat: break
    for f in flat:
        if not f.is_valid: continue
        e = max(f.edges, key=lambda e: e.calc_length()); others = [g for g in e.link_faces if g is not f]
        if len(others) == 1 and others[0] in tris:
            ne = bmesh.utils.edge_rotate(e, True)
            if ne is not None: tris |= set(ne.link_faces); turned += 1; continue
        bmesh.ops.delete(bm, geom=[f], context='FACES_ONLY'); gone += 1
    tris = {f for f in tris if f.is_valid}
bm.normal_update(); left = collections.Counter(len(f.verts) for f in bm.faces); zero = sum(1 for f in bm.faces if f.calc_area() < 1e-7); area1 = sum(f.calc_area() for f in tris if f.is_valid)
thin = sum(1 for f in tris if f.is_valid and 2 * f.calc_area() / max(e.calc_length() for e in f.edges) < 0.01)
n1 = len(bm.faces); bm.to_mesh(me); bm.free(); me.update(); bpy.context.preferences.filepaths.save_version = 0; bpy.ops.wm.save_as_mainfile(filepath=OUT)
print('TRI faces of more than three corners: %d %s, %.1f m2 ; straight-line corners nothing else used, dropped: %d ; flat triangles turned: %d, removed on an open rim: %d' % (sum(sizes.values()), dict(sorted(sizes.items())), area0, nd, turned, gone))
print('TRI now: faces %d -> %d, by corners %s ; their area %.1f m2 ; faces with no area %d ; new triangles thinner than 1 cm %d ; where they were: %s' % (n0, n1, dict(left), area1, zero, thin, cen[:60]))
