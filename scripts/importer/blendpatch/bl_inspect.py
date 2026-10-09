"""Blender with its window, on a LOOK-ONLY copy of mountain_patched.blend: the parts of the diff that are not patches, drawn in colour over the
course, with a numbered marker at each place (select a marker in the outliner, then View > Frame Selected / numpad .)."""
import bpy, pickle, collections
import numpy as np
SP = r'C:\Users\bruno\AppData\Local\Temp\claude\F--Jogos-SEGA-Rally-3\7efd0921-014b-4b6a-8439-6ea64a2cda95\scratchpad\blenddiff'
def load(p):
    D = pickle.load(open(p, 'rb'))
    for d in D['objects']:
        for k, v in list(d.items()):
            if isinstance(v, tuple) and len(v) == 4 and v[0] == 'nd': d[k] = np.frombuffer(v[3], v[1]).reshape(v[2])
    return D
A = load(SP + r'\mountain.pkl')['objects'][0]; B = load(SP + r'\mountain_patched.pkl')['objects'][0]; K = pickle.load(open(SP + r'\final.pkl', 'rb'))
def poly(o, k): s, n = int(o['loop_start'][k]), int(o['loop_total'][k]); return o['co'][o['loop_vert'][s:s + n]]
col = bpy.data.collections.new('DIFF - not patches'); bpy.context.scene.collection.children.link(col)
def mesh(name, polys, colour, wire=True):
    V = []; F = []
    for P in polys: k = len(V); V += [tuple(map(float, p)) for p in P]; F.append(tuple(range(k, k + len(P))))
    me = bpy.data.meshes.new(name); me.from_pydata(V, [], F); me.update(); o = bpy.data.objects.new(name, me); col.objects.link(o)
    o.color = colour; o.show_in_front = True; o.display_type = 'WIRE' if wire else 'SOLID'; o.hide_select = False; return o
def marker(name, at, size):
    e = bpy.data.objects.new(name, None); e.empty_display_type = 'SPHERE'; e.empty_display_size = size; e.location = tuple(map(float, at)); e.show_in_front = True; e.show_name = True; col.objects.link(e); return e
mk = K['moved']
lawn_before = mesh('lawn BEFORE (red) - 58 original grass triangles', [poly(A, k) for k in mk], (1.0, 0.1, 0.1, 1.0))
lawn_after = mesh('lawn AFTER (green) - the same triangles as edited', [poly(B, k) for k in mk], (0.1, 1.0, 0.2, 1.0))
moved_pts = np.array([pb for k in mk for pa, pb in zip(poly(A, k), poly(B, k)) if np.linalg.norm(pa - pb) > 1e-3])
m1 = marker('GO 1 - lawn corners moved 2.2 m (%d corners)' % len(moved_pts), moved_pts.mean(0), max(4.0, float(np.ptp(moved_pts, axis=0).max()) / 2))
deg = K['deg']; mesh('no-area faces (yellow) - %d quads that are only a line' % len(deg), [poly(B, k) for k in deg], (1.0, 0.9, 0.0, 1.0))
# groups of no-area faces that lie together
cen = np.array([poly(B, k).mean(0) for k in deg]); left = list(range(len(deg))); groups = []
while left:
    g = [left.pop(0)]; grew = True
    while grew:
        grew = False
        for j in list(left):
            if np.linalg.norm(cen[g] - cen[j], axis=1).min() < 25.0: g.append(j); left.remove(j); grew = True
    groups.append(g)
groups.sort(key=lambda g: -len(g)); marks = [m1]
for i, g in enumerate(groups): marks.append(marker('GO %d - %d no-area faces' % (i + 2, len(g)), cen[g].mean(0), max(3.0, float(np.ptp(cen[g], axis=0).max()) / 2 + 2.0)))
six = [k for k in K['good'] if int(B['loop_total'][k]) > 4]
for k in six:
    mesh('six-corner face (cyan)', [poly(B, k)], (0.0, 0.9, 1.0, 1.0)); marks.append(marker('GO %d - face with %d corners (is in the patch, needs cutting)' % (len(marks) + 1, int(B['loop_total'][k])), poly(B, k).mean(0), 4.0))
mesh('the 44 real patch faces (white outline)', [poly(B, k) for k in K['good']], (1.0, 1.0, 1.0, 1.0))
road = bpy.data.objects.get("SR3 road (the game's own - hide with H)")
if road: road.hide_set(True)
for o in bpy.data.objects: o.select_set(False)
lawn_before.select_set(True); lawn_after.select_set(True); bpy.context.view_layer.objects.active = lawn_after
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        sp = area.spaces[0]; sp.shading.type = 'SOLID'; sp.shading.light = 'FLAT'; sp.shading.color_type = 'TEXTURE'; sp.shading.wireframe_color_type = 'OBJECT'; sp.clip_end = 6000.0; sp.clip_start = 0.2; sp.overlay.show_floor = False
        for region in area.regions:
            if region.type == 'WINDOW':
                with bpy.context.temp_override(area=area, region=region): bpy.ops.view3d.view_selected()
print('INSPECT markers:', [m.name for m in marks])
