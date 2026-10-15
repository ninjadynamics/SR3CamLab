"""Background Blender: spikes in OUR geometry = a corner standing well above every corner it is joined to, with steep faces all round.
blender -b in.blend --python spikes.py -- list | fix <out.blend>"""
import bpy, bmesh, sys, json, math
import numpy as np
a = sys.argv[sys.argv.index('--') + 1:]; S = __import__('os').environ.get('SR3_SCRATCH', '.').replace(chr(92), '/') + '/'
T = json.load(open(S + 'p3_tiles.json')); ob = bpy.data.objects['1995 course (RAW2)']
if ob.mode == 'EDIT': bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode='OBJECT')
me = ob.data; bm = bmesh.new(); bm.from_mesh(me); dl = bm.verts.layers.deform.verify(); gi = ob.vertex_groups['PATCH'].index
names = [m.name for m in me.materials]; til = [T.get(n.split('_a')[0], n) for n in names]; cut = [t.endswith('_t') or n.endswith('_a') for t, n in zip(til, names)]
def peaks():
    out = []
    for v in bm.verts:
        if gi not in v[dl] or not v.link_faces or any(cut[f.material_index] for f in v.link_faces): continue
        if not all(til[f.material_index].endswith(('c101', 'c106', 'c1A6', 'c0AE', 'c0D6', 'c0D6_dk')) or names[f.material_index].startswith('shade') for f in v.link_faces): continue      # terrain only: a roof's ridge is a peak too
        if any(len(e.link_faces) != 2 for e in v.link_edges) or len(v.link_edges) < 4: continue                     # only corners wholly inside a surface
        nb = [e.other_vert(v) for e in v.link_edges]; dy = np.array([v.co.y - n.co.y for n in nb]); dh = np.array([math.hypot(v.co.x - n.co.x, v.co.z - n.co.z) for n in nb]); sl = dy / np.maximum(dh, 0.05)
        low = dy > 1.0                                                                   # neighbours it stands over
        if low.sum() < max(3, 0.6 * len(nb)) or np.median(dy[low]) < 3.0 or np.median(sl[low]) < 0.8 or dy.min() < -6.5: continue
        # the lower neighbours must lie all round it (a rim of a cliff has them on one side only)
        ang = np.sort(np.arctan2([n.co.z - v.co.z for n, l in zip(nb, low) if l], [n.co.x - v.co.x for n, l in zip(nb, low) if l])); gap = np.max(np.diff(np.r_[ang, ang[0] + 2 * math.pi]))
        if gap > math.radians(200): continue
        out.append((v, float(np.median(dy[low])), float(np.median(sl[low])), len(nb), float(np.average([n.co.y for n, l in zip(nb, low) if l], weights=1.0 / np.maximum(dh[low], 0.1)))))
    return out
found = peaks(); print('SPIKES found %d' % len(found))
for v, md, sl, k, tgt in sorted(found, key=lambda x: -x[1])[:60]: print('SPIKE at (%.1f, %.1f, %.1f): %.1f m over the corners round it, slope %.1f, %d neighbours -> %.1f' % (v.co.x, v.co.y, v.co.z, md, sl, k, tgt + 0.3))
if a[0] == 'fix':
    total = 0; log_ = []
    for rnd in range(6):                                                                 # a peak of two or three corners comes down one corner a round
        fd = peaks()
        if not fd: break
        for v, md, sl, k, tgt in fd: log_.append((round(v.co.x, 1), round(v.co.y, 1), round(v.co.z, 1), round(tgt + 0.3, 1))); v.co.y = tgt + 0.3
        total += len(fd)
    bm.normal_update(); bm.to_mesh(me); me.update(); bpy.ops.wm.save_as_mainfile(filepath=a[1], copy=True); print('SPIKES lowered %d corners: %s -> %s' % (total, log_, a[1]))
