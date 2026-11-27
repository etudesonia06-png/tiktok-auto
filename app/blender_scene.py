"""Exécuté PAR Blender (4.2 LTS) en mode sans écran :

    blender -b --factory-startup -P app/blender_scene.py -- spec.json dossier_images/

Construit un stade, des personnages réutilisables (mascotte lion, supporters, personnages de série),
les anime (bouche synchronisée sur l'enveloppe de la voix, clignements, gestes, rebonds),
place la caméra plan par plan et rend les images avec Cycles sur CPU (aucune carte graphique requise).
"""
import json
import math
import random
import sys

import bpy

ARGS = sys.argv[sys.argv.index("--") + 1:]
SPEC = json.load(open(ARGS[0], encoding="utf-8"))
OUT = ARGS[1].rstrip("/") + "/f_"
FPS = SPEC["fps"]
TOTAL = SPEC["total_frames"]
rnd = random.Random(SPEC.get("seed", 7))


# ---------------------------------------------------------------- utilitaires
def srgb(hexcol: str):
    h = hexcol.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


_MATS = {}


def mat(color, rough=0.45, sheen=0.0, emission=0.0):
    key = (tuple(round(c, 3) for c in color), rough, emission)
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(f"m{len(_MATS)}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = 0.15
    if emission:
        b.inputs["Emission Color"].default_value = (*color, 1)
        b.inputs["Emission Strength"].default_value = emission
    _MATS[key] = m
    return m


def empty(name, loc=(0, 0, 0), parent=None):
    e = bpy.data.objects.new(name, None)
    bpy.context.collection.objects.link(e)
    e.location = loc
    e.parent = parent
    return e


def sphere(loc, r, color, parent, scale=(1, 1, 1), rough=0.45, seg=40):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(0, 0, 0), segments=seg, ring_count=seg // 2)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    o.parent = parent
    o.location = loc
    o.scale = scale
    o.data.materials.append(mat(color, rough))
    return o


def cylinder(loc, r, depth, color, parent, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=(0, 0, 0), vertices=32)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.data.materials.append(mat(color))
    bev = o.modifiers.new("b", "BEVEL")
    bev.width, bev.segments = r * 0.6, 3
    return o


def torus(loc, R, r, color, parent, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, location=(0, 0, 0),
                                     major_segments=48, minor_segments=16)
    o = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    o.parent = parent
    o.location = loc
    o.scale = scale
    o.data.materials.append(mat(color))
    return o


SKINS = ["#f1c27d", "#c68642", "#8d5524", "#e0ac69", "#ffdbac", "#a0522d"]


# ---------------------------------------------------------------- personnages
def face(head_pivot, head_r, skin_front_y, mouth_pos=None, mouth_col=(0.25, 0.02, 0.03)):
    """Yeux (blanc, pupille, reflet) + bouche ; renvoie (bouche, [yeux])."""
    eyes = []
    er = head_r * 0.25
    for sx in (-1, 1):
        w = sphere((sx * head_r * 0.36, skin_front_y * 0.86, head_r * 0.18), er,
                   (0.95, 0.95, 0.95), head_pivot, rough=0.15)
        sphere((0, -er * 0.55, 0), er * 0.58, (0.02, 0.02, 0.02), w, rough=0.1)       # pupille
        sphere((er * 0.2, -er * 1.08, er * 0.25), er * 0.17, (1, 1, 1), w, rough=0.05)  # reflet
        eyes.append(w)
    mouth = sphere(mouth_pos or (0, skin_front_y * 0.98, -head_r * 0.36), head_r * 0.26, mouth_col,
                   head_pivot, scale=(1.3, 0.45, 0.25), rough=0.3)
    return mouth, eyes


def build_supporter(c, root):
    col1, col2 = srgb(c["colors"][0]), srgb(c["colors"][1] if len(c["colors"]) > 1 else "#ffffff")
    skin = srgb(c.get("skin") or rnd.choice(SKINS))
    dark = (0.03, 0.03, 0.05)
    body = empty(c["id"] + "_body", (0, 0, 0), root)
    for sx in (-1, 1):  # jambes + chaussures
        cylinder((sx * 0.2, 0, 0.28), 0.12, 0.5, dark, body)
        sphere((sx * 0.2, -0.08, 0.05), 0.15, (0.9, 0.9, 0.9), body, scale=(1, 1.5, 0.6))
    sphere((0, 0, 0.85), 0.55, col1, body, scale=(1, 0.8, 1.15))          # maillot
    torus((0, 0, 0.9), 0.53, 0.06, col2, body, scale=(1, 0.8, 1))          # bande
    torus((0, 0, 1.38), 0.26, 0.09, col2, body)                            # écharpe
    head = empty(c["id"] + "_head", (0, 0, 1.78), body)
    sphere((0, 0, 0), 0.45, skin, head)
    sphere((0, 0, 0.13), 0.465, col2, head, scale=(1, 1, 0.62))            # bonnet
    sphere((0, 0, 0.47), 0.1, col1, head)                                  # pompon
    for sx in (-1, 1):
        sphere((sx * 0.45, 0, -0.02), 0.09, skin, head)                    # oreilles
    mouth, eyes = face(head, 0.45, -0.42)
    arms = []
    for sx in (-1, 1):
        sh = empty(c["id"] + f"_arm{sx}", (sx * 0.52, 0, 1.18), body)
        cylinder((sx * 0.08, 0, -0.3), 0.09, 0.55, col1, sh, rot=(0, -sx * 0.3, 0))
        sphere((sx * 0.17, 0, -0.6), 0.12, skin, sh)
        arms.append((sh, sx))
    return body, head, mouth, eyes, arms


def build_lion(c, root):
    col = c.get("colors") or ["#ffffff", "#1fa34a", "#f6c21c", "#d62828"]
    fur, mane, cream = (0.92, 0.55, 0.12), (0.55, 0.22, 0.04), (0.98, 0.85, 0.6)
    body = empty(c["id"] + "_body", (0, 0, 0), root)
    for sx in (-1, 1):
        sphere((sx * 0.25, -0.05, 0.12), 0.2, fur, body, scale=(1, 1.3, 0.8))
    sphere((0, 0, 0.75), 0.6, srgb(col[0]), body, scale=(1, 0.85, 1.05))     # maillot
    for i, cc in enumerate(col[1:4]):
        torus((0, 0, 0.62 + i * 0.12), 0.6 - abs(i - 1) * 0.02, 0.05, srgb(cc), body, scale=(1, 0.85, 1))
    head = empty(c["id"] + "_head", (0, 0, 1.75), body)
    for k in range(16):                                                     # crinière
        a = k / 16 * 2 * math.pi
        sphere((math.cos(a) * 0.55, 0.12, math.sin(a) * 0.55), 0.24, mane, head, rough=0.8)
    sphere((0, 0, 0), 0.52, fur, head, rough=0.6)
    sphere((0, -0.43, -0.14), 0.24, cream, head, scale=(1.35, 0.8, 0.8))   # museau
    sphere((0, -0.62, -0.03), 0.08, (0.1, 0.05, 0.04), head, scale=(1.3, 1, 0.8))
    for sx in (-1, 1):
        sphere((sx * 0.38, 0.02, 0.4), 0.13, fur, head)
    mouth, eyes = face(head, 0.52, -0.48, mouth_pos=(0, -0.47, -0.37))
    arms = []
    for sx in (-1, 1):
        sh = empty(c["id"] + f"_arm{sx}", (sx * 0.58, 0, 1.05), body)
        cylinder((sx * 0.08, 0, -0.28), 0.11, 0.5, fur, sh, rot=(0, -sx * 0.3, 0))
        sphere((sx * 0.16, 0, -0.56), 0.14, fur, sh)
        arms.append((sh, sx))
    return body, head, mouth, eyes, arms


BUILDERS = {"lion": build_lion, "supporter": build_supporter, "person": build_supporter}


# ---------------------------------------------------------------- décor
def build_stadium(home_colors):
    # pelouse rayée
    bpy.ops.mesh.primitive_plane_add(size=80, location=(0, 0, 0))
    pitch = bpy.context.active_object
    m = bpy.data.materials.new("pitch")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = 0.9
    sin = nt.nodes.new("ShaderNodeMath"); sin.operation = "SINE"
    gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"; gt.inputs[1].default_value = 0
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    mix.inputs[6].default_value = (0.05, 0.22, 0.04, 1)
    mix.inputs[7].default_value = (0.08, 0.32, 0.06, 1)
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs["Y"], mul.inputs[0])
    nt.links.new(mul.outputs[0], sin.inputs[0])
    nt.links.new(sin.outputs[0], gt.inputs[0])
    nt.links.new(gt.outputs[0], mix.inputs[0])
    nt.links.new(mix.outputs[2], b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = 0.85
    pitch.data.materials.append(m)

    # tribunes : foule de points colorés (Voronoi) sur un grand anneau
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=24, depth=18, location=(0, 0, 9), end_fill_type="NOTHING")
    stands = bpy.context.active_object
    bpy.ops.object.shade_smooth()
    m2 = bpy.data.materials.new("crowd")
    m2.use_nodes = True
    nt2 = m2.node_tree
    b2 = nt2.nodes["Principled BSDF"]
    vor = nt2.nodes.new("ShaderNodeTexVoronoi"); vor.inputs["Scale"].default_value = 140
    ramp = nt2.nodes.new("ShaderNodeValToRGB")
    cols = [srgb(h) for h in home_colors] + [(0.9, 0.9, 0.9), (0.08, 0.08, 0.1), (0.6, 0.1, 0.1)]
    ramp.color_ramp.interpolation = "CONSTANT"
    while len(ramp.color_ramp.elements) < len(cols):
        ramp.color_ramp.elements.new(0.5)
    for i, (el, cc) in enumerate(zip(ramp.color_ramp.elements, cols)):
        el.position = i / len(cols)
        el.color = (*cc, 1)
    sepc = nt2.nodes.new("ShaderNodeSeparateColor")
    nt2.links.new(vor.outputs["Color"], sepc.inputs[0])
    nt2.links.new(sepc.outputs[0], ramp.inputs[0])
    nt2.links.new(ramp.outputs[0], b2.inputs["Base Color"])
    nt2.links.new(ramp.outputs[0], b2.inputs["Emission Color"])
    b2.inputs["Emission Strength"].default_value = 0.35
    stands.data.materials.append(m2)

    # projecteurs
    for x in (-18, 18):
        bpy.ops.object.light_add(type="AREA", location=(x, 6, 16))
        L = bpy.context.active_object
        L.data.energy, L.data.size = 9000, 6
        L.rotation_euler = (math.radians(35), math.radians(-40 if x > 0 else 40), 0)
    bpy.ops.object.light_add(type="SUN", location=(0, -10, 20))
    sun = bpy.context.active_object
    sun.data.energy, sun.data.angle = 2.5, math.radians(8)
    sun.rotation_euler = (math.radians(50), 0, math.radians(15))
    bpy.ops.object.light_add(type="AREA", location=(0, -6, 3))
    fill = bpy.context.active_object
    fill.data.energy, fill.data.size = 600, 5
    fill.rotation_euler = (math.radians(80), 0, 0)
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (0.05, 0.08, 0.2, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = 0.6
    bpy.context.scene.world = w


# ---------------------------------------------------------------- scène
def setup_render():
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = SPEC.get("samples", 12)
    s.cycles.use_adaptive_sampling = True
    s.cycles.use_denoising = True
    try:
        s.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
    s.cycles.max_bounces = 4
    s.cycles.diffuse_bounces = 2
    s.cycles.glossy_bounces = 2
    s.cycles.transparent_max_bounces = 2
    s.render.use_persistent_data = True
    s.render.resolution_x, s.render.resolution_y = SPEC["width"], SPEC["height"]
    s.render.resolution_percentage = 100
    s.render.fps = FPS
    s.render.image_settings.file_format = "JPEG"
    s.render.image_settings.quality = 92
    s.render.filepath = OUT
    s.frame_start, s.frame_end = 1, TOTAL
    for vt in ("AgX", "Filmic"):
        try:
            s.view_settings.view_transform = vt
            break
        except Exception:
            continue
    s.view_settings.look = "None"


def key(obj, path, idx, value, frame):
    getattr(obj, path)[idx] = value
    obj.keyframe_insert(path, index=idx, frame=frame)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    setup_render()
    cast = SPEC["cast"]
    build_stadium(SPEC.get("crowd_colors") or ["#c1272d", "#006233", "#ffffff"])

    actors = {}
    n = len(cast)
    for i, c in enumerate(cast):
        x = (i - (n - 1) / 2) * 1.75
        root = empty(c["id"], (x, 0, 0))
        root.rotation_euler = (0, 0, -x * 0.06)  # léger tournage vers le centre
        parts = BUILDERS.get(c.get("type"), build_supporter)(c, root)
        actors[c["id"]] = (root, x) + parts

    # ---------- animation image par image
    env = SPEC["envelopes"]          # {id: [amplitude 0..1 par image]}
    speaker_at = SPEC["speaker_at"]  # [id parlant par image]
    for cid, (root, x, body, head, mouth, eyes, arms) in actors.items():
        a = env.get(cid, [0.0] * TOTAL)
        ph = rnd.random() * 6.28
        next_blink = rnd.randint(30, 90)
        cheer = SPEC.get("cheer_frames", [])
        for f in range(TOTAL):
            t = f / FPS
            amp = a[f] if f < len(a) else 0.0
            talking = speaker_at[f] == cid if f < len(speaker_at) else False
            excited = f in cheer
            bounce = 0.025 * math.sin(t * 2 * math.pi * 1.1 + ph)
            if talking:
                bounce += 0.06 * amp
            if excited:
                bounce += 0.18 * abs(math.sin(t * 2 * math.pi * 2.2 + ph))
            key(body, "location", 2, bounce, f + 1)
            key(mouth, "scale", 2, 0.22 + (1.5 * amp if talking else 0.0), f + 1)
            key(head, "rotation_euler", 0, (0.12 * amp if talking else 0.0) + 0.03 * math.sin(t * 1.3 + ph), f + 1)
            key(head, "rotation_euler", 2, 0.08 * math.sin(t * 0.7 + ph) + (0.1 if talking else 0.0) * math.sin(t * 2.1), f + 1)
            # clignements
            blink = 0.1 if next_blink <= f < next_blink + 3 else 1.0
            if f >= next_blink + 3:
                next_blink = f + rnd.randint(int(FPS * 2), int(FPS * 4.5))
            for e in eyes:
                key(e, "scale", 2, blink, f + 1)
            # bras : gestes quand il parle, bras levés quand ça célèbre
            for sh, sx in arms:
                # rotation autour de Y : un angle de signe -sx écarte le bras vers l'extérieur
                if excited:
                    ang = -sx * (2.6 + 0.3 * math.sin(t * 9 + ph))
                elif talking:
                    ang = -sx * (0.35 + 0.45 * amp + 0.2 * math.sin(t * 3 + ph + sx))
                else:
                    ang = -sx * (0.12 + 0.05 * math.sin(t * 1.4 + ph))
                key(sh, "rotation_euler", 1, ang, f + 1)

    # ---------- caméra plan par plan (avec léger travelling avant)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 38
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 2.2
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    target = empty("cam_target")
    tr = cam.constraints.new("TRACK_TO")
    tr.target, tr.track_axis, tr.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    cam_data.dof.focus_object = target
    spread = (n - 1) * 1.75
    for shot in SPEC["shots"]:
        s0, s1 = shot["start"] + 1, max(shot["end"], shot["start"] + 1)
        if shot["type"] == "wide":
            tx, tz, cy, cz = 0.0, 1.35, -(5.4 + spread * 0.9), 2.1
            cx = 0.0
        else:
            tx = actors[shot["speaker"]][1] if shot["speaker"] in actors else 0.0
            tz, cy, cz, cx = 1.65, -3.3, 1.85, tx * 0.85
        for fr, dy in ((s0, 0.0), (s1, 0.35)):
            key(target, "location", 0, tx, fr)
            key(target, "location", 2, tz, fr)
            key(cam, "location", 0, cx, fr)
            key(cam, "location", 1, cy + dy, fr)
            key(cam, "location", 2, cz, fr)
    for o in (cam, target):
        if o.animation_data and o.animation_data.action:
            for fc in o.animation_data.action.fcurves:
                for kp in fc.keyframe_points:
                    kp.interpolation = "LINEAR"

    if SPEC.get("save_blend"):
        bpy.ops.wm.save_as_mainfile(filepath=SPEC["save_blend"])
    if SPEC.get("preview_frame"):
        bpy.context.scene.frame_set(SPEC["preview_frame"])
        bpy.context.scene.render.filepath = OUT + "preview"
        bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(animation=True)


main()
