"""Module responsible for appending and preparing PCB shaders."""

import bpy
import os
import math
import gerber2blend.modules.config as config
import gerber2blend.modules.custom_utilities as cu
import gerber2blend.modules.file_io as fio
from wand.image import Image  # type: ignore
from wand.color import Color  # type: ignore
from gerber2blend.modules.config import (
    GBR_F_SILK,
    GBR_B_SILK,
    GBR_F_MASK,
    GBR_B_MASK,
    GBR_F_CU,
    GBR_B_CU,
    OUT_F_DISPMAP,
    OUT_B_DISPMAP,
    OUT_F_SOLDER,
    OUT_B_SOLDER,
)
import logging
from typing import List, Tuple, Literal

logger = logging.getLogger(__name__)


def load_materials(mat_list: List[str]) -> None:
    """Load materials from other blendfile using predefined list."""
    imported_materials = fio.import_from_blendfile(config.mat_blend_path, "materials", lambda name: name in mat_list)

    for material in imported_materials:
        logger.debug(f"Loading material {material}")


def reload_textures(texture: str) -> None:
    """Refresh image saved at filepath."""
    for image in bpy.data.images:
        logger.debug(image.filepath)
    bpy.data.images[texture].filepath = config.png_path + texture
    logger.debug("Reloading textures: " + bpy.data.images[texture].filepath)


def append_material(obj: bpy.types.Object, mat: str) -> None:
    """Append material to object's material slots."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    used_mat = bpy.data.materials[mat]
    assert isinstance(obj.data, bpy.types.Mesh)
    obj.data.materials.append(used_mat)


def assign_material(
    obj: bpy.types.Object, mat_name: str, pos: Literal["top", "bot", "edge"], vrts: None | List[Tuple[float]] = None
) -> None:
    """Assign material to a material slot."""
    if vrts is None:
        vrts = []
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


def find_idx(obj: bpy.types.Object, matname: str) -> int:
    """Find object's material slot index occupied by material of specified name."""
    for i in range(len(obj.material_slots)):
        if obj.material_slots[i].name == matname:
            return i
    return 0


def create_inner_layer_material(mat_name: str, png: str) -> None:
    """Create inner copper layer shader."""
    in_mat = bpy.data.materials.get("main_pcb_inner")
    assert in_mat is not None, "Failed to load `main_pcb_inner` material"
    in_copy = in_mat.copy()
    in_copy.name = mat_name
    # update Cu texture
    image_cu = in_copy.node_tree.nodes["Image Texture.001"]  # type:ignore [attr-defined]
    bpy.ops.image.open(filepath=config.png_path + png)
    image_cu.image = bpy.data.images[png]


def to_blender_color(c: float) -> float:
    """Convert RGB to Blender gamma corrected color."""
    c = min(max(0, c), 255) / 255
    return c / 12.92 if c < 0.04045 else math.pow((c + 0.055) / 1.055, 2.4)


def hex_to_rgba(hex_value: int | str, alpha: float) -> Tuple[float, float, float, float]:
    """Convert color hex value to RGBA format."""
    if isinstance(hex_value, str):
        hex_value = int(hex_value, 16)
        # hex_value = hex(hex_value)
    b = to_blender_color((hex_value & 0xFF))
    g = to_blender_color((hex_value >> 8) & 0xFF)
    r = to_blender_color((hex_value >> 16) & 0xFF)
    return (r, g, b, alpha)


def set_soldermask_color(soldermask_color: Tuple[str, str]) -> None:
    """Set color of soldermask shader node.

    Preset or pair of hex values - first value for masked RGB node, second value for unmasked RGB node.
    """
    colors_dict = {
        "Black": [0x211918, 0x150E02],
        "White": [0xFFFFFF, 0x9A9393],
        "Green": [0x027029, 0x073E14],
        "Blue": [0x02346D, 0x102141],
        "Red": [0xD01B10, 0x83140B],
    }
    masked_color_val: int = 0
    if len(soldermask_color[0]) == 2:  # custom colors
        masked_color_val = int(str(soldermask_color[0][0]), 16)
        unmasked_color_val = int(str(soldermask_color[0][1]), 16)
    else:
        [masked_color_val, unmasked_color_val] = colors_dict[soldermask_color[0]]  # preset color used

    masked_color_node = bpy.data.node_groups["Color_group"].nodes["Masked_Color"]
    unmasked_color_node = bpy.data.node_groups["Color_group"].nodes["Unmasked_Color"]

    masked_color_node.outputs[0].default_value = hex_to_rgba(masked_color_val, 1.0)  # type: ignore
    unmasked_color_node.outputs[0].default_value = hex_to_rgba(unmasked_color_val, 1.0)  # type: ignore


def set_silkscreen_color(silk_color: str) -> None:
    """Set color of silkscreen shader node (black or white)."""
    colors_dict = {"Black": 0x000000, "White": 0xB3BEC2}
    mix_node = bpy.data.node_groups["Color_group"].nodes["Mix"]
    mix_node.inputs["A"].default_value = hex_to_rgba(colors_dict[silk_color[0]], 1.0)  # type: ignore


def process_edge_materials(
    pcb: bpy.types.Object, plated_verts: List[Tuple[float]], bare_verts: List[Tuple[float]]
) -> None:
    """Assign gold or edge material to model sides."""
    materials = ["main_pcb_edge_gold", "main_pcb_edge_bare"]
    load_materials(materials)

    for material in materials:
        append_material(pcb, material)

    assign_material(pcb, "main_pcb_edge_gold", "edge", plated_verts)
    assign_material(pcb, "main_pcb_edge_bare", "edge", bare_verts)


def process_materials(board_col: bpy.types.Collection, in_list: List[str]) -> None:
    """Assign top and bottom materials to model."""
    materials = ["main_pcb_top", "main_pcb_bot", "main_pcb_inner"]
    load_materials(materials)

    # Set different color of soldermask
    set_soldermask_color(config.blendcfg["SETTINGS"]["SOLDERMASK"])
    set_silkscreen_color(config.blendcfg["SETTINGS"]["SILKSCREEN"])

    with Color("white") as bg:
        with Image(width=100, height=100, background=bg) as img:
            # white image as OUT_*_SOLDER will not introduce changes in texture color
            fsolder = config.png_path + OUT_F_SOLDER + ".png"
            if not os.path.exists(fsolder):
                img.save(filename=fsolder)
            bsolder = config.png_path + OUT_B_SOLDER + ".png"
            if not os.path.exists(bsolder):
                img.save(filename=bsolder)

    textures = [
        f"{OUT_F_DISPMAP}.png",
        f"{GBR_F_SILK}.png",
        f"{GBR_F_MASK}.png",
        f"{GBR_F_CU}.png",
        f"{OUT_F_SOLDER}.png",
        f"{OUT_B_DISPMAP}.png",
        f"{GBR_B_SILK}.png",
        f"{GBR_B_MASK}.png",
        f"{GBR_B_CU}.png",
        f"{OUT_B_SOLDER}.png",
    ]

    layers_materials = ["main_pcb_bot"]
    if config.blendcfg["EFFECTS"]["STACKUP"]:
        for i, png in enumerate(in_list):
            mat_name = "main_pcb_inner" + str(i + 1)
            create_inner_layer_material(mat_name, png)
            layers_materials.append(mat_name)
            materials.append(mat_name)

    layers_materials += ["main_pcb_top"]

    # update paths to pngs
    for t in textures:
        reload_textures(t)
    # assign materials to PCB layers
    for i, board_layer in enumerate(board_col.objects):
        append_material(board_layer, layers_materials[i])
        append_material(board_layer, layers_materials[i + 1])
        assign_material(board_layer, layers_materials[i], "bot")
        assign_material(board_layer, layers_materials[i + 1], "top")


def clear_and_set_solder_material(obj: bpy.types.Object) -> None:
    """Clear all materials and add solder material instead."""
    obj.data.materials.clear()  # type:ignore
    material = "Solder"
    load_materials([material])
    append_material(obj, material)
