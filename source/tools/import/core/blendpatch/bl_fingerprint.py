"""Blender, headless: the exact stored bytes of everything that makes up the scene's geometry and look, as hashes.
    blender -b <file.blend> --python bl_fingerprint.py -- <out.json>"""
import bpy, sys, json, hashlib
import numpy as np
h = lambda a: hashlib.sha1(np.ascontiguousarray(a).tobytes()).hexdigest()
out = {'objects': {}, 'materials': {}, 'images': {}}
for o in sorted(bpy.data.objects, key=lambda x: x.name):
    if o.type != 'MESH': out['objects'][o.name] = {'type': o.type}; continue
    me = o.data; d = {'type': 'MESH', 'vertices': len(me.vertices), 'faces': len(me.polygons), 'loops': len(me.loops), 'edges': len(me.edges)}
    co = np.empty(len(me.vertices) * 3, np.float32); me.vertices.foreach_get('co', co); d['vertex positions (float32 bytes)'] = h(co)
    for name, n, attr, typ in (('face loop start', len(me.polygons), 'loop_start', np.int32), ('face corner count', len(me.polygons), 'loop_total', np.int32), ('face material index', len(me.polygons), 'material_index', np.int32)):
        a = np.empty(n, typ); me.polygons.foreach_get(attr, a); d[name] = h(a)
    a = np.empty(len(me.loops), np.int32); me.loops.foreach_get('vertex_index', a); d['corner -> vertex'] = h(a)
    a = np.empty(len(me.edges) * 2, np.int32); me.edges.foreach_get('vertices', a); d['edges'] = h(a)
    d['uv layers'] = {}
    for u in me.uv_layers: a = np.empty(len(me.loops) * 2, np.float32); u.data.foreach_get('uv', a); d['uv layers'][u.name] = h(a)
    d['material slots'] = [s.material.name if s.material else None for s in o.material_slots]
    d['matrix'] = h(np.array(o.matrix_world, np.float32)); d['hidden'] = bool(o.hide_get()) if o.name in bpy.context.view_layer.objects else None
    d['vertex groups'] = {}
    for g in o.vertex_groups:
        idx = [v.index for v in me.vertices if any(x.group == g.index for x in v.groups)]; d['vertex groups'][g.name] = [len(idx), h(np.array(idx, np.int32))]
    d['other attributes'] = sorted(a.name for a in me.attributes)
    out['objects'][o.name] = d
for m in sorted(bpy.data.materials, key=lambda x: x.name):
    nodes = []
    if m.use_nodes:
        for n in sorted(m.node_tree.nodes, key=lambda x: x.name):
            e = [n.bl_idname, n.name]
            if n.type == 'TEX_IMAGE': e += [n.image.name if n.image else None, n.interpolation]
            if n.type == 'BSDF_PRINCIPLED': e += [round(float(n.inputs['Roughness'].default_value), 6)]
            nodes.append(e)
        nodes.append(sorted((l.from_node.name, l.from_socket.name, l.to_node.name, l.to_socket.name) for l in m.node_tree.links))
    out['materials'][m.name] = hashlib.sha1(json.dumps(nodes).encode()).hexdigest()
for i in sorted(bpy.data.images, key=lambda x: x.name):
    out['images'][i.name] = [list(i.size), hashlib.sha1(bytes(i.packed_file.data)).hexdigest() if i.packed_file else 'not packed']
json.dump(out, open(sys.argv[sys.argv.index('--') + 1], 'w'), indent=1, sort_keys=True); print('fingerprint written', len(out['objects']), 'objects', len(out['materials']), 'materials', len(out['images']), 'images')
