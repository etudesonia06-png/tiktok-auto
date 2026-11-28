"""Exécuté PAR Blender (4.2 LTS ou plus récent) en mode sans écran :

    blender -b --factory-startup -P app/blender_scene.py -- spec.json dossier_images/

Construit un décor (stade, studio parisien ou rue de Paris la nuit), des personnages réutilisables
(mascotte lion, supporters, personnages de la série), les anime (bouche synchronisée sur la voix,
regards et corps tournés vers celui qui parle, sourcils expressifs, clignements, respiration, gestes),
place la caméra plan par plan (plans larges, rapprochés, contre-plongée, plans de réaction, plans à deux)
et rend les images avec Cycles sur CPU (aucune carte graphique requise).
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
SETTING = SPEC.get("setting", "stadium")
rnd = random.Random(SPEC.get("seed", 7))


# ---------------------------------------------------------------- utilitaires
def srgb(hexcol: str):
    h = hexcol.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


_MATS = {}


def mat(color, rough=0.45, emission=0.0, coat=0.15):
    key = (tuple(round(c, 3) for c in color), rough, emission, coat)
    if key in _MATS:
        return _MATS[key]
    m = bpy.data.materials.new(f"m{len(_MATS)}")
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    if "Coat Weight" in b.inputs:
        b.inputs["Coat Weight"].default_value = coat
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


def _finish(o, loc, parent, material, rot=(0, 0, 0), scale=(1, 1, 1), smooth=True):
    if smooth:
        bpy.ops.object.shade_smooth()
    o.parent = parent
    o.location = loc
    o.rotation_euler = rot
    o.scale = scale
    if material is not None:
        o.data.materials.append(material)
    return o


def sphere(loc, r, color, parent, scale=(1, 1, 1), rough=0.45, seg=24, emission=0.0):
    bpy.ops.mesh.primitive_uv_sphere_add(radius=r, location=(0, 0, 0), segments=seg, ring_count=seg // 2)
    return _finish(bpy.context.active_object, loc, parent, mat(color, rough, emission), scale=scale)


def cylinder(loc, r, depth, color, parent, rot=(0, 0, 0), bevel=True, verts=24, scale=(1, 1, 1), emission=0.0):
    bpy.ops.mesh.primitive_cylinder_add(radius=r, depth=depth, location=(0, 0, 0), vertices=verts)
    o = _finish(bpy.context.active_object, loc, parent, mat(color, emission=emission), rot=rot, scale=scale)
    if bevel:
        bev = o.modifiers.new("b", "BEVEL")
        bev.width, bev.segments = min(r * 0.6, depth * 0.3), 3
    return o


def cone(loc, r1, r2, depth, color, parent, rot=(0, 0, 0), emission=0.0, verts=24):
    bpy.ops.mesh.primitive_cone_add(radius1=r1, radius2=r2, depth=depth, location=(0, 0, 0), vertices=verts)
    return _finish(bpy.context.active_object, loc, parent, mat(color, emission=emission), rot=rot)


def torus(loc, R, r, color, parent, scale=(1, 1, 1), rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=R, minor_radius=r, location=(0, 0, 0),
                                     major_segments=40, minor_segments=12)
    return _finish(bpy.context.active_object, loc, parent, mat(color), scale=scale, rot=rot)


def box(loc, size, color, parent=None, rough=0.6, emission=0.0, material=None, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
    o = _finish(bpy.context.active_object, loc, parent, material or mat(color, rough, emission),
                scale=size, smooth=False)
    if bevel:
        b = o.modifiers.new("b", "BEVEL")
        b.width, b.segments = bevel, 2
    return o


def plane(loc, size, material, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 0, 0))
    return _finish(bpy.context.active_object, loc, None, material, rot=rot,
                   scale=(size[0], size[1], 1), smooth=False)


def rgba_inputs(node):
    """Entrées couleur A et B d'un nœud Mix (compatible Blender 4.x et 5.x)."""
    return [i for i in node.inputs if i.type == "RGBA"][:2]


def rgba_output(node):
    return next(o for o in node.outputs if o.type == "RGBA")


SKINS = ["#f1c27d", "#c68642", "#8d5524", "#e0ac69", "#ffdbac", "#a0522d"]
HAIR = (0.025, 0.018, 0.014)
GREY = (0.45, 0.45, 0.47)


# ---------------------------------------------------------------- visages
def face(head, r, front_y, skin, mouth_pos=None, nose=True, brow_col=HAIR):
    """Yeux (blanc, iris, pupille, reflet), sourcils, nez, bouche.
    Renvoie (bouche, yeux, sourcils)."""
    eyes, brows = [], []
    er = r * 0.24
    for sx in (-1, 1):
        w = sphere((sx * r * 0.36, front_y * 0.84, r * 0.16), er, (0.96, 0.96, 0.96), head, rough=0.15)
        sphere((0, -er * 0.8, 0), er * 0.56, (0.22, 0.11, 0.04), w, scale=(1, 0.45, 1), rough=0.1)   # iris
        sphere((0, -er * 0.97, 0), er * 0.3, (0.01, 0.01, 0.01), w, scale=(1, 0.35, 1), rough=0.05)  # pupille
        sphere((er * 0.2, -er * 1.08, er * 0.22), er * 0.12, (1, 1, 1), w, rough=0.02, emission=0.6)  # reflet
        eyes.append(w)
        bp = empty(head.name + f"_brow{sx}", (sx * r * 0.36, front_y * 0.93, r * 0.44), head)
        cylinder((0, 0, 0), er * 0.22, er * 1.6, brow_col, bp, rot=(0, math.pi / 2, sx * -0.12), bevel=False,
                 verts=10)
        brows.append((bp, sx))
    if nose:
        sphere((0, front_y * 1.02, -r * 0.05), r * 0.13, tuple(c * 0.85 for c in skin), head, scale=(1, 1.1, 0.9))
    mouth = sphere(mouth_pos or (0, front_y * 0.95, -r * 0.4), r * 0.24, (0.28, 0.03, 0.05),
                   head, scale=(1.35, 0.5, 0.25), rough=0.3)
    sphere((0, 0.01, 0.06), r * 0.2, (0.95, 0.92, 0.9), mouth, scale=(0.9, 0.6, 0.4))  # dents
    return mouth, eyes, brows


def hair(head, r, style, col, col2):
    """Coiffures et accessoires réutilisables."""
    if style in ("short", "grey_moustache", "beard", "ponytail", "curly"):
        hc = GREY if style == "grey_moustache" else HAIR
        sphere((0, r * 0.14, r * 0.34), r * 1.0, hc, head, scale=(1.03, 1.02, 0.72), rough=0.8)
    if style == "curly":
        for k in range(14):
            a = k / 14 * 2 * math.pi
            sphere((math.cos(a) * r * 0.62, r * 0.1 + math.sin(a) * r * 0.45, r * 0.72), r * 0.26, HAIR, head,
                   rough=0.9, seg=12)
    if style == "ponytail":
        sphere((0, r * 1.0, r * 0.1), r * 0.3, HAIR, head, scale=(0.8, 1, 1.5), rough=0.8)
    if style == "beard":
        sphere((0, -r * 0.25, -r * 0.55), r * 0.62, HAIR, head, scale=(1.05, 0.75, 0.6), rough=0.9)
    if style == "grey_moustache":
        sphere((0, -r * 0.98, -r * 0.26), r * 0.2, GREY, head, scale=(1.8, 0.6, 0.5), rough=0.9)
    if style == "scarf":  # foulard
        sphere((0, r * 0.22, r * 0.1), r * 1.1, col2, head, scale=(1.04, 1, 1.08), rough=0.7)
        torus((0, -r * 0.42, -r * 0.02), r * 0.86, r * 0.12, col2, head, scale=(0.95, 1, 1.12),
              rot=(math.radians(80), 0, 0))
    if style == "cap":  # casquette
        sphere((0, r * 0.06, r * 0.5), r * 1.02, col, head, scale=(1, 1, 0.6), rough=0.6)
        cylinder((0, -r * 0.9, r * 0.58), r * 0.5, r * 0.06, col2, head, rot=(math.radians(-10), 0, 0),
                 scale=(1, 0.9, 1), bevel=False)


# ---------------------------------------------------------------- personnages
def build_human(c, root, supporter):
    col1, col2 = srgb(c["colors"][0]), srgb(c["colors"][1] if len(c["colors"]) > 1 else "#ffffff")
    skin = srgb(c.get("skin") or rnd.choice(SKINS))
    dark = (0.03, 0.03, 0.05)
    pants = (0.05, 0.07, 0.14) if not supporter else dark
    body = empty(c["id"] + "_body", (0, 0, 0), root)
    for sx in (-1, 1):  # jambes + chaussures
        cylinder((sx * 0.19, 0, 0.3), 0.12, 0.55, pants, body)
        sphere((sx * 0.19, -0.08, 0.06), 0.15, (0.92, 0.92, 0.92) if supporter else (0.2, 0.12, 0.08), body,
               scale=(1, 1.5, 0.6))
    torso = empty(c["id"] + "_torso", (0, 0, 0.62), body)
    sphere((0, 0, 0.25), 0.52, col1, torso, scale=(1, 0.78, 1.15), rough=0.7)       # maillot / haut
    if supporter:
        torus((0, 0, 0.28), 0.5, 0.06, col2, torso, scale=(1, 0.8, 1))               # bande
        torus((0, 0, 0.76), 0.25, 0.09, col2, torso)                                 # écharpe
        cylinder((0.12, -0.33, 0.6), 0.07, 0.4, col2, torso, rot=(0.2, 0, 0.1), bevel=False)
    else:
        torus((0, 0, 0.76), 0.22, 0.06, col2, torso)                                 # col
    head = empty(c["id"] + "_head", (0, 0, 1.16), torso)
    sphere((0, 0, 0), 0.45, skin, head, rough=0.5)
    for sx in (-1, 1):
        sphere((sx * 0.45, 0, -0.02), 0.09, skin, head)                              # oreilles
    style = c.get("hair", "short")
    if supporter:
        if style in ("ponytail",):
            sphere((0, 0.47, 0.0), 0.14, HAIR, head, scale=(0.8, 1, 1.6), rough=0.8)
        if style == "beard":
            sphere((0, -0.11, -0.25), 0.28, HAIR, head, scale=(1.05, 0.75, 0.6), rough=0.9)
        sphere((0, 0.03, 0.36), 0.47, col2, head, scale=(1, 1, 0.47), rough=0.8)     # bonnet
        torus((0, 0.02, 0.25), 0.375, 0.045, col1, head)
        sphere((0, 0, 0.6), 0.1, col1, head, rough=0.9)                              # pompon
    else:
        hair(head, 0.45, style, col1, col2)
    mouth, eyes, brows = face(head, 0.45, -0.42, skin,
                              brow_col=GREY if style == "grey_moustache" else HAIR)
    arms = []
    for sx in (-1, 1):
        sh = empty(c["id"] + f"_arm{sx}", (sx * 0.5, 0, 0.58), torso)
        cylinder((sx * 0.08, 0, -0.3), 0.09, 0.55, col1, sh, rot=(0, -sx * 0.3, 0))
        sphere((sx * 0.17, 0, -0.6), 0.12, skin, sh)
        arms.append((sh, sx))
    return body, torso, head, mouth, eyes, brows, arms


def build_lion(c, root):
    col = c.get("colors") or ["#ffffff", "#1fa34a", "#f6c21c", "#d62828"]
    fur, mane, cream = (0.92, 0.55, 0.12), (0.55, 0.22, 0.04), (0.98, 0.85, 0.6)
    body = empty(c["id"] + "_body", (0, 0, 0), root)
    for sx in (-1, 1):
        sphere((sx * 0.25, -0.05, 0.12), 0.2, fur, body, scale=(1, 1.3, 0.8), rough=0.7)
    cone((0.35, 0.45, 0.35), 0.04, 0.02, 0.8, fur, body, rot=(0.9, 0.6, 0))                # queue
    sphere((0.62, 0.75, 0.62), 0.1, mane, body, rough=0.9)
    torso = empty(c["id"] + "_torso", (0, 0, 0.5), body)
    sphere((0, 0, 0.25), 0.6, srgb(col[0]), torso, scale=(1, 0.85, 1.05), rough=0.6)     # maillot
    for i, cc in enumerate(col[1:4]):
        torus((0, 0, 0.12 + i * 0.12), 0.6 - abs(i - 1) * 0.02, 0.05, srgb(cc), torso, scale=(1, 0.85, 1))
    head = empty(c["id"] + "_head", (0, 0, 1.25), torso)
    for ring, (rr, nn, sz) in enumerate(((0.6, 18, 0.24), (0.42, 12, 0.22))):            # crinière en 2 couches
        for k in range(nn):
            a = k / nn * 2 * math.pi + ring * 0.2
            sphere((math.cos(a) * rr, 0.16 + ring * 0.1, math.sin(a) * rr), sz, mane, head, rough=0.9, seg=14)
    sphere((0, 0, 0), 0.52, fur, head, rough=0.6)
    sphere((0, -0.43, -0.14), 0.24, cream, head, scale=(1.35, 0.8, 0.8))                 # museau
    sphere((0, -0.63, -0.03), 0.08, (0.1, 0.05, 0.04), head, scale=(1.3, 1, 0.8), rough=0.2)
    for sx in (-1, 1):
        sphere((sx * 0.4, 0.02, 0.42), 0.14, fur, head, rough=0.7)                       # oreilles
        sphere((sx * 0.4, -0.04, 0.42), 0.08, cream, head)
        for k in range(3):                                                               # moustaches
            cylinder((sx * 0.36, -0.52, -0.12 + k * 0.05), 0.006, 0.3, (0.95, 0.95, 0.9), head,
                     rot=(0, math.pi / 2, sx * (0.15 - k * 0.12)), bevel=False, verts=6)
    mouth, eyes, brows = face(head, 0.52, -0.48, fur, mouth_pos=(0, -0.47, -0.37), nose=False, brow_col=mane)
    arms = []
    for sx in (-1, 1):
        sh = empty(c["id"] + f"_arm{sx}", (sx * 0.58, 0, 0.55), torso)
        cylinder((sx * 0.08, 0, -0.28), 0.11, 0.5, fur, sh, rot=(0, -sx * 0.3, 0))
        sphere((sx * 0.16, 0, -0.56), 0.14, fur, sh, rough=0.7)
        arms.append((sh, sx))
    return body, torso, head, mouth, eyes, brows, arms


def build_character(c, root):
    t = c.get("type")
    if t == "lion":
        return build_lion(c, root)
    return build_human(c, root, supporter=(t == "supporter"))


# ---------------------------------------------------------------- décors
def world(color, strength):
    w = bpy.data.worlds.new("w")
    w.use_nodes = True
    w.node_tree.nodes["Background"].inputs[0].default_value = (*color, 1)
    w.node_tree.nodes["Background"].inputs[1].default_value = strength
    bpy.context.scene.world = w


def light(kind, loc, energy, rot=(0, 0, 0), size=1.0, color=(1, 1, 1)):
    bpy.ops.object.light_add(type=kind, location=loc)
    L = bpy.context.active_object
    L.data.energy = energy
    L.data.color = color
    if kind == "AREA":
        L.data.size = size
    elif kind in ("POINT", "SPOT"):
        L.data.shadow_soft_size = size
    L.rotation_euler = rot
    return L


def striped(name, c1, c2, scale, axis="Y", rough=0.85):
    """Matériau à bandes (pelouse, parquet)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    tc = nt.nodes.new("ShaderNodeTexCoord")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    mul = nt.nodes.new("ShaderNodeMath"); mul.operation = "MULTIPLY"; mul.inputs[1].default_value = scale
    sin = nt.nodes.new("ShaderNodeMath"); sin.operation = "SINE"
    gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"; gt.inputs[1].default_value = 0
    mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"
    a, bb = rgba_inputs(mix)
    a.default_value, bb.default_value = (*c1, 1), (*c2, 1)
    nt.links.new(tc.outputs["Object"], sep.inputs[0])
    nt.links.new(sep.outputs[axis], mul.inputs[0])
    nt.links.new(mul.outputs[0], sin.inputs[0])
    nt.links.new(sin.outputs[0], gt.inputs[0])
    nt.links.new(gt.outputs[0], mix.inputs[0])
    nt.links.new(rgba_output(mix), b.inputs["Base Color"])
    b.inputs["Roughness"].default_value = rough
    return m


def windows_material(name, wall, lit, scale=6.0, glow=1.2):
    """Façade avec fenêtres éclairées (texture briques détournée)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    br = nt.nodes.new("ShaderNodeTexBrick")
    br.inputs["Color1"].default_value = (*lit, 1)
    br.inputs["Color2"].default_value = (0.02, 0.02, 0.04, 1)
    br.inputs["Mortar"].default_value = (*wall, 1)
    br.inputs["Scale"].default_value = scale
    br.inputs["Mortar Size"].default_value = 0.09
    br.inputs["Brick Width"].default_value = 0.45
    br.inputs["Row Height"].default_value = 0.5
    br.offset = 0.0
    inv = nt.nodes.new("ShaderNodeMath"); inv.operation = "SUBTRACT"; inv.inputs[0].default_value = 1.0
    em = nt.nodes.new("ShaderNodeMath"); em.operation = "MULTIPLY"; em.inputs[1].default_value = glow
    nt.links.new(br.outputs["Color"], b.inputs["Base Color"])
    nt.links.new(br.outputs["Color"], b.inputs["Emission Color"])
    nt.links.new(br.outputs["Fac"], inv.inputs[1])
    nt.links.new(inv.outputs[0], em.inputs[0])
    nt.links.new(em.outputs[0], b.inputs["Emission Strength"])
    b.inputs["Roughness"].default_value = 0.8
    return m


def eiffel(loc, s, parent=None):
    """Tour Eiffel stylisée, illuminée (silhouette dorée)."""
    gold = (1.0, 0.62, 0.18)
    root = empty("eiffel", loc, parent)
    root.scale = (s, s, s)
    for sx in (-1, 1):
        for sy in (-1, 1):
            cone((sx * 0.55, sy * 0.55, 0.9), 0.16, 0.05, 1.9, gold, root,
                 rot=(sy * 0.28, -sx * 0.28, 0), emission=3.0, verts=8)
    box((0, 0, 1.75), (1.25, 1.25, 0.12), gold, root, emission=3.0)
    cone((0, 0, 3.2), 0.42, 0.06, 2.9, gold, root, emission=3.0, verts=8)
    box((0, 0, 3.5), (0.55, 0.55, 0.08), gold, root, emission=3.0)
    cylinder((0, 0, 5.0), 0.04, 0.7, gold, root, emission=4.0, bevel=False, verts=8)
    sphere((0, 0, 5.4), 0.08, (1, 1, 0.9), root, emission=12.0, seg=10)
    return root


def build_stadium(home_colors):
    plane((0, 0, 0), (90, 90), striped("pitch", (0.05, 0.22, 0.04), (0.08, 0.32, 0.06), 0.9))
    white = mat((0.9, 0.9, 0.9), 0.6)
    torus((0, 9, 0.01), 4.5, 0.06, (0.9, 0.9, 0.9), None, scale=(1, 1, 0.05))          # rond central
    box((0, 9, 0.01), (40, 0.12, 0.02), None, material=white)                          # ligne médiane
    for sx in (-1, 1):                                                                 # but au fond
        cylinder((sx * 3.6, 22, 1.2), 0.08, 2.4, (0.95, 0.95, 0.95), None, bevel=False)
    cylinder((0, 22, 2.4), 0.08, 7.3, (0.95, 0.95, 0.95), None, rot=(0, math.pi / 2, 0), bevel=False)
    # panneaux LED aux couleurs des équipes
    for i, x in enumerate(range(-18, 19, 6)):
        col = srgb(home_colors[i % len(home_colors)])
        box((x, 15, 0.55), (5.8, 0.25, 0.9), col, emission=2.5)
    # tribunes : foule de points colorés (Voronoi) sur un grand anneau
    bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=26, depth=18, location=(0, 0, 9),
                                        end_fill_type="NOTHING")
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
    # projecteurs (pylônes lumineux visibles dans le fond)
    for x in (-18, 18):
        light("AREA", (x, 6, 16), 9000, rot=(math.radians(35), math.radians(-40 if x > 0 else 40), 0), size=6)
        box((x * 1.25, 24, 19), (3.5, 0.3, 1.4), (1, 1, 0.95), emission=8.0)
    sun = light("SUN", (0, -10, 20), 2.5, rot=(math.radians(50), 0, math.radians(15)))
    sun.data.angle = math.radians(8)
    light("AREA", (0, -6, 3), 600, rot=(math.radians(80), 0, 0), size=5)
    light("AREA", (0, 4, 4), 900, rot=(math.radians(-60), 0, 0), size=6, color=(0.7, 0.8, 1.0))  # contre-jour
    world((0.05, 0.08, 0.2), 0.6)


def build_apartment(accent):
    """Petit studio parisien le soir : parquet, mur, fenêtre sur la tour Eiffel, lit, bureau, lampe."""
    plane((0, 0, 0), (16, 16), striped("parquet", (0.32, 0.18, 0.08), (0.4, 0.24, 0.11), 3.2, axis="X", rough=0.5))
    wall = mat((0.78, 0.7, 0.6), 0.9)
    box((0, 3.0, 5.0), (16, 0.2, 10), None, material=wall)                              # mur du fond
    for sx in (-1, 1):
        box((sx * 6.5, 0, 5.0), (0.2, 12, 10), None, material=wall)                     # murs latéraux
    box((0, 2.88, 0.12), (16, 0.06, 0.24), (0.95, 0.95, 0.92))                          # plinthe
    # fenêtre : vue de nuit sur Paris
    sky = bpy.data.materials.new("night")
    sky.use_nodes = True
    nt = sky.node_tree
    b = nt.nodes["Principled BSDF"]
    grad = nt.nodes.new("ShaderNodeTexGradient")
    tc = nt.nodes.new("ShaderNodeTexCoord")
    mp = nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Rotation"].default_value = (0, 0, math.pi / 2)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.55, 0.22, 0.28, 1)
    ramp.color_ramp.elements[1].color = (0.03, 0.05, 0.16, 1)
    nt.links.new(tc.outputs["Generated"], mp.inputs[0])
    nt.links.new(mp.outputs[0], grad.inputs[0])
    nt.links.new(grad.outputs["Fac"], ramp.inputs[0])
    nt.links.new(ramp.outputs[0], b.inputs["Emission Color"])
    nt.links.new(ramp.outputs[0], b.inputs["Base Color"])
    b.inputs["Emission Strength"].default_value = 1.5
    plane((-1.6, 2.86, 3.0), (3.2, 2.6), sky, rot=(math.pi / 2, 0, 0))
    roofs = windows_material("roofs", (0.08, 0.08, 0.12), (1.0, 0.78, 0.4), scale=14, glow=1.5)
    for i, (x, h) in enumerate(((-2.8, 0.7), (-2.0, 0.95), (-1.0, 0.6), (-0.3, 0.85))):
        box((x, 2.84, 1.7 + h / 2), (0.75, 0.02, h), None, material=roofs)
    eiffel((-1.2, 2.845, 1.75), 0.42).scale[1] = 0.02
    frame = mat((0.95, 0.95, 0.95), 0.4)
    for z in (1.7, 4.3):
        box((-1.6, 2.8, z), (3.4, 0.12, 0.12), None, material=frame)
    for x in (-3.3, -1.6, 0.1):
        box((x, 2.8, 3.0), (0.12, 0.12, 2.7), None, material=frame)
    # lit + bureau + lampe + étagère + affiches
    box((3.9, 1.6, 0.3), (2.4, 2.2, 0.6), (0.3, 0.2, 0.14), bevel=0.04)
    box((3.9, 1.6, 0.68), (2.3, 2.1, 0.2), srgb(accent), rough=0.9, bevel=0.06)
    box((3.9, 2.45, 0.9), (1.4, 0.4, 0.3), (0.95, 0.95, 0.95), rough=0.9, bevel=0.1)
    box((-4.6, 2.3, 0.75), (2.4, 1.0, 0.08), (0.45, 0.28, 0.14), bevel=0.02)
    for x in (-5.6, -3.6):
        box((x, 2.3, 0.37), (0.08, 0.9, 0.74), (0.3, 0.2, 0.1))
    box((-4.8, 2.45, 0.98), (0.6, 0.35, 0.4), (0.1, 0.1, 0.12), bevel=0.02)           # ordinateur
    box((-4.8, 2.25, 0.82), (0.55, 0.3, 0.04), (0.12, 0.12, 0.14))
    cylinder((-3.9, 2.5, 1.05), 0.03, 0.55, (0.15, 0.15, 0.15), None, bevel=False)
    cone((-3.9, 2.45, 1.38), 0.22, 0.1, 0.25, (1, 0.85, 0.5), None, emission=6.0)
    light("POINT", (-3.9, 2.2, 1.3), 120, size=0.3, color=(1, 0.75, 0.45))
    box((2.0, 2.82, 3.6), (2.2, 0.25, 0.08), (0.45, 0.28, 0.14))                       # étagère
    for i, cc in enumerate(((0.7, 0.1, 0.1), (0.1, 0.3, 0.6), (0.9, 0.7, 0.1), (0.1, 0.5, 0.3))):
        box((1.3 + i * 0.35, 2.82, 3.82), (0.18, 0.2, 0.36), cc)
    for x, cc in ((2.0, srgb(accent)), (4.5, (0.1, 0.45, 0.35))):
        box((x, 2.88, 2.4), (1.0, 0.04, 1.4), cc, emission=0.4)                         # affiches
    light("AREA", (-2.5, -4.5, 4.0), 1100, rot=(math.radians(60), 0, math.radians(-25)), size=4,
          color=(1, 0.88, 0.75))
    light("AREA", (-1.6, 2.3, 3.0), 250, rot=(math.radians(-90), 0, 0), size=3, color=(0.5, 0.6, 1.0))
    light("AREA", (3.5, -2.0, 3.5), 350, rot=(math.radians(55), 0, math.radians(35)), size=3, color=(1, 0.8, 0.6))
    world((0.02, 0.02, 0.04), 0.4)


def build_street():
    """Rue de Paris la nuit : deux rangées d'immeubles haussmanniens éclairés qui fuient vers
    la tour Eiffel illuminée, réverbères, bitume mouillé."""
    plane((0, 30, 0), (60, 120), mat((0.045, 0.045, 0.055), 0.3, coat=0.5))            # bitume mouillé
    walk = mat((0.3, 0.28, 0.26), 0.8)
    facade = windows_material("facade", (0.36, 0.3, 0.23), (1.0, 0.72, 0.35), scale=3.0, glow=2.0)
    roof = mat((0.16, 0.18, 0.22), 0.5)
    for side in (-1, 1):
        box((side * 5.2, 30, 0.08), (2.4, 120, 0.16), None, material=walk)             # trottoirs
        y = -6.0
        while y < 75:
            d = rnd.uniform(6, 9)
            h = rnd.uniform(11, 15)
            box((side * 8.6, y + d / 2, h / 2), (4.4, d - 0.2, h), None, material=facade)
            box((side * 8.4, y + d / 2, h + 0.8), (4.0, d - 0.4, 1.6), None, material=roof)  # toit en zinc
            y += d
        for y in (-2.0, 6.0, 14.0, 22.0, 34.0, 46.0):                                  # réverbères
            cylinder((side * 4.4, y, 2.0), 0.06, 4.0, (0.04, 0.05, 0.04), None, bevel=False)
            sphere((side * 4.4, y, 4.1), 0.2, (1, 0.85, 0.55), None, emission=10.0, seg=16)
            if y < 15:
                light("POINT", (side * 4.2, y, 3.9), 300, size=0.4, color=(1, 0.75, 0.45))
    eiffel((0, 95, 0), 10.0)
    light("AREA", (-2.5, -6, 4.5), 800, rot=(math.radians(62), 0, math.radians(-20)), size=5,
          color=(0.85, 0.9, 1.0))
    light("AREA", (0, 6, 3.5), 300, rot=(math.radians(-75), 0, 0), size=6, color=(1.0, 0.7, 0.45))
    world((0.025, 0.04, 0.12), 0.9)


# ---------------------------------------------------------------- rendu
def setup_render():
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = SPEC.get("samples", 12)
    s.cycles.use_adaptive_sampling = True
    s.cycles.use_denoising = True
    for attr, val in (("denoiser", "OPENIMAGEDENOISE"), ("denoising_prefilter", "FAST"),
                      ("denoising_input_passes", "RGB_ALBEDO")):
        try:
            setattr(s.cycles, attr, val)
        except Exception:
            pass
    s.cycles.adaptive_threshold = 0.08
    s.cycles.max_bounces = 3
    s.cycles.diffuse_bounces = 1
    s.cycles.glossy_bounces = 1
    s.cycles.caustics_reflective = False
    s.cycles.caustics_refractive = False
    s.cycles.transparent_max_bounces = 2
    s.render.use_persistent_data = True
    s.render.resolution_x, s.render.resolution_y = SPEC["width"], SPEC["height"]
    s.render.resolution_percentage = 100
    s.render.fps = FPS
    s.render.image_settings.file_format = "JPEG"
    s.render.image_settings.quality = 92
    s.render.filepath = OUT
    s.frame_start = SPEC.get("frame_start", 1)
    s.frame_end = min(SPEC.get("frame_end", TOTAL), TOTAL)
    for vt in ("AgX", "Filmic"):
        try:
            s.view_settings.view_transform = vt
            break
        except Exception:
            continue
    try:
        s.view_settings.look = "AgX - Medium High Contrast"
    except Exception:
        s.view_settings.look = "None"


def key(obj, path, idx, value, frame):
    getattr(obj, path)[idx] = value
    obj.keyframe_insert(path, index=idx, frame=frame)


def smooth(prev, target, k):
    return prev + (target - prev) * k


def ease(u):
    return u * u * (3 - 2 * u)


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    setup_render()
    cast = SPEC["cast"]
    colors = SPEC.get("crowd_colors") or ["#c1272d", "#006233", "#ffffff"]
    if SETTING == "apartment":
        build_apartment(colors[0])
    elif SETTING == "street":
        build_street()
    else:
        build_stadium(colors)

    actors = {}
    n = len(cast)
    for i, c in enumerate(cast):
        x = (i - (n - 1) / 2) * 1.75
        y = 0.25 * abs(i - (n - 1) / 2)  # léger arc de cercle
        root = empty(c["id"], (x, y, 0))
        k = c.get("height", 1.0)
        root.scale = (k, k, k)
        parts = build_character(c, root)
        head_z = (1.78 if c.get("type") != "lion" else 1.75) * k
        actors[c["id"]] = {"root": root, "x": x, "y": y, "head_z": head_z, "parts": parts}

    # ---------- animation image par image
    env = SPEC["envelopes"]          # {id: [amplitude 0..1 par image]}
    speaker_at = SPEC["speaker_at"]  # [id parlant par image]
    cheer = set(SPEC.get("cheer_frames", []))
    emph = SPEC.get("emphasis", [])
    for cid, A in actors.items():
        root, x = A["root"], A["x"]
        body, torso, head, mouth, eyes, brows, arms = A["parts"]
        a = env.get(cid, [0.0] * TOTAL)
        ph = rnd.random() * 6.28
        next_blink = rnd.randint(20, 60)
        turn = head_turn = look = 0.0
        brow = 0.0
        gesture_until, gesture_side = -1, 1
        for f in range(TOTAL):
            t = f / FPS
            amp = a[f] if f < len(a) else 0.0
            sp = speaker_at[f] if f < len(speaker_at) else ""
            talking = sp == cid
            excited = f in cheer
            # --- orientation : celui qui écoute se tourne vers celui qui parle
            if talking or sp not in actors:
                tgt_turn, tgt_look = -x * 0.08, 0.0
            else:
                dx = actors[sp]["x"] - x
                tgt_turn = max(-0.55, min(0.55, 0.32 * dx))
                tgt_look = max(-0.35, min(0.35, 0.2 * dx))
            turn = smooth(turn, tgt_turn, 0.12)
            head_turn = smooth(head_turn, tgt_turn * 0.6, 0.2)
            look = smooth(look, tgt_look + (0.06 * math.sin(t * 0.9 + ph) if not talking else 0.0), 0.35)
            key(root, "rotation_euler", 2, turn, f + 1)
            # --- corps : respiration, rebond, saut de joie
            bounce = 0.02 * math.sin(t * 2 * math.pi * 1.1 + ph) + (0.05 * amp if talking else 0.0)
            if excited:
                bounce += 0.22 * abs(math.sin(t * 2 * math.pi * 2.0 + ph))
            key(body, "location", 2, bounce, f + 1)
            key(torso, "scale", 2, 1.0 + 0.02 * math.sin(t * 2 * math.pi * 0.28 + ph), f + 1)
            key(torso, "rotation_euler", 0, (0.06 * amp if talking else 0.0) - (0.05 if excited else 0.0), f + 1)
            # --- tête : hochements quand il parle, petits acquiescements quand il écoute
            nod = 0.12 * amp if talking else 0.04 * max(0.0, math.sin(t * 2.4 + ph)) ** 8
            key(head, "rotation_euler", 0, nod + 0.03 * math.sin(t * 1.3 + ph), f + 1)
            key(head, "rotation_euler", 1, 0.05 * math.sin(t * 0.8 + ph) * (1.6 if talking else 1.0), f + 1)
            key(head, "rotation_euler", 2, head_turn + 0.06 * math.sin(t * 0.7 + ph), f + 1)
            # --- bouche : ouverture sur l'enveloppe, forme variable (voyelles)
            shape = 0.5 + 0.5 * math.sin(t * 17 + ph)
            key(mouth, "scale", 2, 0.22 + (1.6 * amp if talking else 0.0), f + 1)
            key(mouth, "scale", 0, 1.35 - (0.35 * amp * shape if talking else 0.0) + (0.25 if excited else 0), f + 1)
            # --- yeux : clignements + regard
            blink = 0.08 if next_blink <= f < next_blink + max(2, FPS // 6) else 1.0
            if f >= next_blink + max(2, FPS // 6):
                next_blink = f + rnd.randint(int(FPS * 2), int(FPS * 4.5))
            for e in eyes:
                key(e, "scale", 2, blink, f + 1)
                key(e, "rotation_euler", 2, look, f + 1)
            # --- sourcils : levés sur les mots forts et les pics de voix, froncés quand il écoute
            hot = any(0 <= f - e0 < FPS * 1.2 for e0 in emph) and talking
            tgt_brow = 0.06 if (hot or excited) else (0.03 * amp if talking else -0.01)
            brow = smooth(brow, tgt_brow, 0.3)
            for bp, sx in brows:
                key(bp, "delta_location", 2, brow, f + 1)
                key(bp, "rotation_euler", 1, sx * (0.25 * brow), f + 1)
            # --- bras : gestes amples quand il parle (parfois il pointe l'autre), bras levés en célébration
            if talking and f > gesture_until and amp > 0.7 and rnd.random() < 0.05:
                gesture_until, gesture_side = f + int(FPS * 1.2), rnd.choice((-1, 1))
            for sh, sx in arms:
                fwd = 0.0
                if excited:
                    ang = -sx * (2.6 + 0.3 * math.sin(t * 9 + ph))
                elif talking:
                    ang = -sx * (0.35 + 0.45 * amp + 0.2 * math.sin(t * 3 + ph + sx))
                    if f <= gesture_until and sx == gesture_side:
                        ang, fwd = -sx * 0.5, -1.2  # bras tendu vers l'avant
                else:
                    ang = -sx * (0.12 + 0.05 * math.sin(t * 1.4 + ph))
                key(sh, "rotation_euler", 1, ang, f + 1)
                key(sh, "rotation_euler", 0, fwd, f + 1)

    # ---------- caméra plan par plan (mouvements doux, léger effet caméra à l'épaule)
    cam_data = bpy.data.cameras.new("cam")
    cam_data.lens = 38
    cam_data.dof.use_dof = True
    cam_data.dof.aperture_fstop = 2.4
    cam = bpy.data.objects.new("cam", cam_data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    target = empty("cam_target")
    tr = cam.constraints.new("TRACK_TO")
    tr.target, tr.track_axis, tr.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    cam_data.dof.focus_object = target
    spread = (n - 1) * 1.75

    def pos(cid):
        A = actors.get(cid)
        return (A["x"], A["y"], A["head_z"]) if A else (0.0, 0.0, 1.8)

    def framing(shot):
        """Renvoie ((cible départ, caméra départ), (cible fin, caméra fin))."""
        kind = shot["type"]
        sx, sy, hz = pos(shot["speaker"])
        lx, ly, lz = pos(shot.get("listener", shot["speaker"]))
        side = 1 if lx >= sx else -1
        if kind == "wide_push":
            return (((0, 0, 1.55), (0, -(6.4 + spread), 1.6)), ((0, 0, 1.5), (0, -(4.9 + spread * 0.8), 1.35)))
        if kind == "wide":
            return (((0, 0, 1.5), (0, -(5.3 + spread * 0.9), 1.5)), ((0, 0, 1.5), (0, -(4.9 + spread * 0.9), 1.55)))
        if kind == "medium":
            return (((sx, sy, hz - 0.45), (sx * 0.8, -4.1, hz - 0.1)), ((sx, sy, hz - 0.4), (sx * 0.8, -3.7, hz - 0.1)))
        if kind == "low":  # contre-plongée « héroïque »
            return (((sx, sy, hz - 0.1), (sx * 0.9 - side * 0.4, -2.9, 0.75)),
                    ((sx, sy, hz - 0.05), (sx * 0.9 - side * 0.5, -2.6, 0.8)))
        if kind == "over":  # trois-quarts, depuis le côté de l'interlocuteur
            return (((sx, sy, hz - 0.08), (sx + side * 1.7, -2.6, hz + 0.1)),
                    ((sx, sy, hz - 0.05), (sx + side * 1.5, -2.4, hz + 0.1)))
        if kind == "reaction":
            return (((lx, ly, lz - 0.05), (lx * 0.85, -2.9, lz + 0.05)), ((lx, ly, lz - 0.05), (lx * 0.85, -2.6, lz + 0.05)))
        if kind == "two":
            mx = (sx + lx) / 2
            d = abs(sx - lx)
            return (((mx, 0, 1.55), (mx, -(3.4 + d * 0.9), 1.85)), ((mx, 0, 1.55), (mx, -(3.2 + d * 0.9), 1.85)))
        # close (défaut)
        return (((sx, sy, hz - 0.08), (sx * 0.85, -3.0, hz + 0.08)), ((sx, sy, hz - 0.05), (sx * 0.85, -2.65, hz + 0.08)))

    for shot in SPEC["shots"]:
        s0, s1 = shot["start"], max(shot["end"], shot["start"])
        (t0, c0), (t1, c1) = framing(shot)
        L = max(1, s1 - s0)
        cam_data.dof.aperture_fstop = 5.6 if shot["type"] in ("wide", "wide_push", "two") else 3.2
        for fr in (s0 + 1, s1 + 1):  # valeur constante sur tout le plan
            cam_data.dof.keyframe_insert("aperture_fstop", frame=fr)
        for f in range(s0, s1 + 1):
            u = ease((f - s0) / L)
            tt = f / FPS
            shake = (0.012 * math.sin(tt * 1.7) + 0.006 * math.sin(tt * 4.3),
                     0.008 * math.sin(tt * 1.1 + 1.0),
                     0.01 * math.sin(tt * 2.3 + 2.0))
            for i in range(3):
                key(target, "location", i, t0[i] + (t1[i] - t0[i]) * u, f + 1)
                key(cam, "location", i, c0[i] + (c1[i] - c0[i]) * u + shake[i], f + 1)

    if SPEC.get("save_blend"):
        bpy.ops.wm.save_as_mainfile(filepath=SPEC["save_blend"])
    if SPEC.get("preview_frames"):
        for fr in SPEC["preview_frames"]:
            bpy.context.scene.frame_set(fr)
            bpy.context.scene.render.filepath = f"{OUT}preview_{fr:04d}"
            bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(animation=True)


main()
