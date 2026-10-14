"""Blender, headless: every mesh object of a .blend as plain arrays (world-space corners, material and uv per face).
    blender -b <file.blend> --python bl_dump.py -- <out.pkl>
tri_loops / tri_poly: Blender's own triangles of every face (a face of more than three corners is cut the way Blender draws it)."""
import bpy, sys, pickle
import numpy as np
out = sys.argv[sys.argv.index('--') + 1]; objs = []
for o in bpy.data.objects:                                             # a scene saved while in edit mode: left (in memory only), so the mesh arrays are whole
    if o.type == 'MESH' and o.mode == 'EDIT': bpy.context.view_layer.objects.active = o; bpy.ops.object.mode_set(mode='OBJECT')
for o in bpy.data.objects:
    if o.type != 'MESH': continue
    me = o.data; M = np.array(o.matrix_world); nv = len(me.vertices); co = np.empty(nv * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
    W = co @ M[:3, :3].T + M[:3, 3]
    cl = np.empty(nv * 3, np.float32); me.vertices.foreach_get('co', cl); cl = cl.reshape(-1, 3)          # the stored numbers themselves
    npoly = len(me.polygons); ls = np.empty(npoly, np.int32); lt = np.empty(npoly, np.int32); mi = np.empty(npoly, np.int32)
    me.polygons.foreach_get('loop_start', ls); me.polygons.foreach_get('loop_total', lt); me.polygons.foreach_get('material_index', mi)
    lv = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', lv)
    uv = None
    if me.uv_layers.active: uv = np.empty(len(me.loops) * 2); me.uv_layers.active.data.foreach_get('uv', uv); uv = uv.reshape(-1, 2)
    mats = [s.material.name if s.material else None for s in o.material_slots]
    me.calc_loop_triangles(); nt = len(me.loop_triangles); tl = np.empty(nt * 3, np.int32); tp = np.empty(nt, np.int32); me.loop_triangles.foreach_get('loops', tl); me.loop_triangles.foreach_get('polygon_index', tp)
    ne = len(me.edges); ev = np.empty(ne * 2, np.int32); me.edges.foreach_get('vertices', ev)
    objs.append(dict(name=o.name, co_local=cl, hidden=bool(o.hide_get() if hasattr(o, 'hide_get') else False), matrix=M, co=W, loop_start=ls, loop_total=lt, mat_index=mi, loop_vert=lv, uv=uv, mats=mats, edges=ev.reshape(-1, 2), tri_loops=tl.reshape(-1, 3), tri_poly=tp,
                     modifiers=[m.type for m in o.modifiers]))
for d in objs:
    for k, v in list(d.items()):
        if isinstance(v, np.ndarray): d[k] = ('nd', str(v.dtype), v.shape, v.tobytes())      # (Blender's numpy 2 pickles do not load in numpy 1)
pickle.dump(dict(file=bpy.data.filepath, objects=objs, images=[(i.name, tuple(i.size)) for i in bpy.data.images]), open(out, 'wb'), protocol=4)
print('dumped', [(d['name'], len(d['co']), len(d['loop_total'])) for d in objs])
