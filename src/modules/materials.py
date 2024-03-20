import bpy  # type: ignore
import math
import modules.config as config
import modules.custom_utilities as cu
import modules.fileIO as fio
from modules.config import (
    GBR_F_SILK,
    GBR_B_SILK,
    GBR_F_MASK,
    GBR_B_MASK,
    GBR_F_CU,
    GBR_B_CU,
    OUT_F_DISPMAP,
    OUT_B_DISPMAP,
)
import logging

logger = logging.getLogger(__name__)


def load_materials(mat_list):
    """Load materials from other blendfile using predefined list"""

    imported_materials = fio.import_from_blendfile(
        config.mat_blend_path, "materials", lambda name: name in mat_list
    )

    for material in imported_materials:
        logger.debug(f"Loading material {material}")


def reload_textures(texture):
    """Refresh image saved at filepath"""

    for image in bpy.data.images:
        logger.debug(image.filepath)
    bpy.data.images[texture].filepath = config.png_path + texture
    logger.debug("Reloading textures: " + bpy.data.images[texture].filepath)


def append_material(obj, mat):
    """Append material to object's material slots"""

    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    used_mat = bpy.data.materials[mat]
    obj.data.materials.append(used_mat)


def assign_material(obj, mat_name, pos, vrts=[]):
    """Assign material to a material slot"""

    cu.face_desel(obj)
    cu.face_sel(obj, pos, vrts)
    bpy.context.object.active_material_index = find_idx(obj, mat_name)
    bpy.ops.object.material_slot_assign()
    if pos == "edge":  # smooth shading of board edges
        bpy.ops.mesh.faces_shade_smooth()
    cu.face_desel(obj)
    bpy.ops.mesh.select_mode(type="VERT")
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")


def find_idx(obj, matname):
    """Find object's material slot index occupied by material of specified name"""

    for i in range(len(obj.material_slots)):
        if obj.material_slots[i].name == matname:
            return i


def create_inner_layer_material(mat_name, png):
    """Create inner copper layer shader"""

    in_mat = bpy.data.materials.get("main_pcb_inner")
    in_copy = in_mat.copy()
    in_copy.name = mat_name
    # update Cu texture
    image_cu = in_copy.node_tree.nodes["Image Texture.001"]
    bpy.ops.image.open(filepath=config.png_path + png)
    image_cu.image = bpy.data.images[png]


def to_blender_color(c):
    """Convert RGB to Blender gamma corrected color"""

    c = min(max(0, c), 255) / 255
    return c / 12.92 if c < 0.04045 else math.pow((c + 0.055) / 1.055, 2.4)


def hex_to_rgba(hex_value, alpha):
    """Convert color hex value to RGBA format"""

    if isinstance(hex_value, str):
        hex_value = int(hex_value, 16)
        # hex_value = hex(hex_value)
    b = to_blender_color((hex_value & 0xFF))
    g = to_blender_color((hex_value >> 8) & 0xFF)
    r = to_blender_color((hex_value >> 16) & 0xFF)
    return (r, g, b, alpha)


def set_soldermask_color(soldermask_color):
    """Set color of soldermask shader node (preset or pair of hex values - first value for ColorRamp node, second value for Mix node)"""
    colors_dict = {
        "Black": [0x211918, 0x150E02],
        "White": [0xFFFFFF, 0x9A9393],
        "Green": [0x027029, 0x073E14],
        "Blue": [0x02346D, 0x102141],
        "Red": [0xD01B10, 0x83140B],
    }
    if len(soldermask_color) == 2:
        [ramp_val, mix_val] = soldermask_color  # custom colors
    else:
        [ramp_val, mix_val] = colors_dict[soldermask_color[0]]  # preset color used

    color_ramp_node = bpy.data.node_groups["Color_group"].nodes["ColorRamp.003"]
    mix_node = bpy.data.node_groups["Color_group"].nodes["Mix.002"]

    color_ramp_node.color_ramp.elements[1].color = hex_to_rgba(ramp_val, 1.0)
    mix_node.inputs[1].default_value = hex_to_rgba(mix_val, 1.0)


def set_silkscreen_color(silk_color):
    """Set color of silkscreen shader node (black or white)"""

    colors_dict = {"Black": 0x000000, "White": 0xB3BEC2}
    mix_node = bpy.data.node_groups["Color_group"].nodes["Mix"]
    mix_node.inputs[1].default_value = hex_to_rgba(colors_dict[silk_color[0]], 1.0)


def process_edge_materials(pcb, plated_verts, bare_verts):
    """Assign gold or edge material to model sides"""

    materials = ["main_pcb_gold", "main_pcb_edge"]
    load_materials(materials)

    for material in materials:
        append_material(pcb, material)

    assign_material(pcb, "main_pcb_gold", "edge", plated_verts)
    assign_material(pcb, "main_pcb_edge", "edge", bare_verts)


def process_materials(board_col, In_list):
    """Assign top and bottom materials to model"""

    materials = ["main_pcb_top", "main_pcb_bot", "main_pcb_inner"]
    load_materials(materials)

    # Set different color of soldermask
    set_soldermask_color(config.blendcfg["SETTINGS"]["SOLDERMASK"])
    set_silkscreen_color(config.blendcfg["SETTINGS"]["SILKSCREEN"])

    textures = [
        f"{OUT_F_DISPMAP}.png",
        f"{GBR_F_SILK}.png",
        f"{GBR_F_MASK}.png",
        f"{GBR_F_CU}.png",
        f"{OUT_B_DISPMAP}.png",
        f"{GBR_B_SILK}.png",
        f"{GBR_B_MASK}.png",
        f"{GBR_B_CU}.png",
    ]
    for t in textures:
        reload_textures(t)

    layers_materials = ["main_pcb_bot"]
    for i, png in enumerate(In_list):
        mat_name = "main_pcb_inner" + str(i + 1)
        create_inner_layer_material(mat_name, png)
        layers_materials.append(mat_name)
        materials.append(mat_name)
    layers_materials += ["main_pcb_top"]

    for i, pcb in enumerate(board_col.objects):
        for material in materials:
            append_material(pcb, material)

        assign_material(pcb, layers_materials[i], "bot")
        assign_material(pcb, layers_materials[i + 1], "top")


def clear_empty_material_slots():
    """Clears empty slots in all objects on scene"""

    for object in bpy.data.objects:
        bpy.context.view_layer.objects.active = object
        for slot in object.material_slots:
            if not slot.material:
                bpy.context.object.active_material_index = slot.slot_index
                bpy.ops.object.material_slot_remove()
