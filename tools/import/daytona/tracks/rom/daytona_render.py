"""Headless Blender stills of an exported Daytona USA course (flat: the tiles' own colours, no lighting).

    blender.exe -b --factory-startup --python daytona_render.py -- <course.obj> <views.json> <out folder> [engine]

views.json: [{"name": "...", "pos": [x, y, z], "target": [x, y, z], "lens": 24}, ...] in GAME axes (x, y up, z forward);
an entry with "ortho": <width in m> renders a straight-down plan instead.
The OBJ stores (x, y, -z); Blender imports it as (x, z_game, y).
"""
import bpy, sys, os, json, math, mathutils
argv = sys.argv[sys.argv.index("--") + 1:]
OBJ, VIEWS, OUT = argv[0], argv[1], argv[2]
os.makedirs(OUT, exist_ok=True)
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.wm.obj_import(filepath=OBJ, forward_axis="NEGATIVE_Z", up_axis="Y")

for m in bpy.data.materials:
    if not m.use_nodes: continue
    nt = m.node_tree
    img = None; kd = (0.8, 0.8, 0.8, 1.0)
    for n in nt.nodes:
        if n.type == "TEX_IMAGE" and img is None: img = n.image
        if n.type == "BSDF_PRINCIPLED": kd = tuple(n.inputs["Base Color"].default_value)
    for n in list(nt.nodes): nt.nodes.remove(n)
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    em = nt.nodes.new("ShaderNodeEmission")
    half = m.name.endswith("_ck") or "_ck_" in m.name
    if img is not None:
        t = nt.nodes.new("ShaderNodeTexImage"); t.image = img; t.interpolation = "Closest"
        nt.links.new(t.outputs["Color"], em.inputs["Color"])
        tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader")
        nt.links.new(t.outputs["Alpha"], mix.inputs[0]); nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs["Surface"])
    else:
        em.inputs["Color"].default_value = kd
        if half:
            tr = nt.nodes.new("ShaderNodeBsdfTransparent"); mix = nt.nodes.new("ShaderNodeMixShader"); mix.inputs[0].default_value = 0.5
            nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs["Surface"])
        else:
            nt.links.new(em.outputs[0], out.inputs["Surface"])
    m.use_backface_culling = False
    for attr, val in (("surface_render_method", "DITHERED"), ("blend_method", "HASHED")):
        try: setattr(m, attr, val)
        except Exception: pass

w = bpy.data.worlds.new("sky"); w.use_nodes = True
w.node_tree.nodes["Background"].inputs[0].default_value = (0.30, 0.50, 0.85, 1); w.node_tree.nodes["Background"].inputs[1].default_value = 1.0
sc.world = w
cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam")); sc.collection.objects.link(cam); sc.camera = cam
cam.data.clip_start = 0.3; cam.data.clip_end = 20000
names = [e.identifier for e in bpy.types.RenderSettings.bl_rna.properties["engine"].enum_items]
eng = argv[3] if len(argv) > 3 else ("BLENDER_EEVEE_NEXT" if "BLENDER_EEVEE_NEXT" in names else "BLENDER_EEVEE")
sc.render.engine = eng
sc.render.resolution_x = 1280; sc.render.resolution_y = 720
sc.view_settings.view_transform = "Standard"
try: sc.eevee.taa_render_samples = 16
except Exception: pass
sc.render.film_transparent = False


def g2b(p): return mathutils.Vector((p[0], p[2], p[1]))


for v in json.load(open(VIEWS)):
    pos = g2b(v["pos"]); tgt = g2b(v["target"])
    cam.location = pos
    if v.get("ortho"):
        cam.data.type = "ORTHO"; cam.data.ortho_scale = v["ortho"]
        cam.rotation_euler = (0, 0, 0)
    else:
        cam.data.type = "PERSP"; cam.data.lens = v.get("lens", 24)
        cam.rotation_euler = (tgt - pos).to_track_quat("-Z", "Y").to_euler()
    sc.render.resolution_x = v.get("w", 1280); sc.render.resolution_y = v.get("h", 720)
    sc.render.filepath = os.path.join(OUT, v["name"] + ".png")
    bpy.ops.render.render(write_still=True)
    print("rendered", v["name"])
print("done")
