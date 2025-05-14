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
    if config.blendcfg["SETTINGS"]["GENERATE_GLTF"]:
        edge_gold_material = "gltf_main_pcb_edge_gold"
        edge_bare_material = "gltf_main_pcb_edge_bare"
    else:
        edge_gold_material = "main_pcb_edge_gold"
        edge_bare_material = "main_pcb_edge_bare"
    materials = [edge_gold_material, edge_bare_material]
    load_materials(materials)

    for material in materials:
        append_material(pcb, material)

    assign_material(pcb, edge_gold_material, "edge", plated_verts)
    assign_material(pcb, edge_bare_material, "edge", bare_verts)


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

    if config.blendcfg["SETTINGS"]["GENERATE_GLTF"]:
        convert_pcb_materials_to_gltf_format(board_col)


def setup_gpu() -> None:
    """Find compatible GPU devices and enable them for rendering. If no suitable GPU is found, use CPU instead."""
    cycles_preferences = bpy.context.preferences.addons["cycles"].preferences
    cycles_preferences.refresh_devices()  # type: ignore
    logger.debug(f"Available devices: {[device for device in cycles_preferences.devices]}")  # type: ignore
    gpu_types = [
        "CUDA",
        "OPTIX",
        "HIP",
        "ONEAPI",
        "METAL",
    ]

    try:
        device = next((dev for dev in cycles_preferences.devices if dev.type in gpu_types))  # type: ignore
        bpy.context.scene.cycles.device = "GPU"
        cycles_preferences.compute_device_type = device.type  # type: ignore
        logger.info(f"Enabled GPU rendering with: {device.name}.")
    except StopIteration:
        device = next((dev for dev in cycles_preferences.devices if dev.type == "CPU"), None)  # type: ignore
        bpy.context.scene.cycles.device = "CPU"
        cycles_preferences.compute_device_type = "NONE"  # type: ignore
        logger.info(f"No GPU device found, enabled CPU rendering with: {device.name}")
    device.use = True


def init_render_settings() -> None:
    """Set up initial renderer properties for texture baking."""
    logger.info("Setting up initial render properties for texture baking...")
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 50
    scene.cycles.use_denoising = True

    setup_gpu()


def create_image_node(node_name: str, nodes: bpy.types.Nodes, img_res: List[int], color: bool = True) -> bpy.types.Node:
    """Create Image node with new texture."""
    image = bpy.data.images.new(node_name, height=img_res[1], width=img_res[0], is_data=color)
    image.filepath_raw = f"{config.pcb_gltf_textures_path}{node_name}.png"
    image.file_format = "PNG"
    texture_node = nodes.new("ShaderNodeTexImage")
    texture_node.name = node_name
    texture_node.image = image  # type:ignore
    return texture_node


def bake_texture(image_node: bpy.types.Node, nodes: bpy.types.Nodes, bake_type: str) -> None:
    """Bake given texture property."""
    logger.info(f"Baking {image_node.name} texture...")
    image_node.select = True
    nodes.active = image_node
    with fio.stdout_redirected():
        bpy.ops.object.bake(type=bake_type, save_mode="EXTERNAL")
    image = image_node.image  # type:ignore
    image.save()
    image.pack()
    cu.make_image_paths_relative(image)
    nodes.active = None  # type:ignore
    image_node.select = False


def apply_baked_texture(gltf_nodes: bpy.types.Nodes, node_name: str, image: bpy.types.Image) -> None:
    """Substitute template textures with baked textures."""
    image_node = gltf_nodes.get(node_name)
    image_node.image = image  # type:ignore


def make_gltf_compatibile_shader(
    object_with_texture: bpy.types.Object, material: bpy.types.Material, img_res: List[int]
) -> bpy.types.Material:
    """Make a single shader gltf-compatibile and rename it."""
    bpy.context.view_layer.objects.active = object_with_texture
    object_with_texture.select_set(True)
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    color_image_node = create_image_node(f"gltf_{config.PCB_name}_{material.name}_color", nodes, img_res, False)
    metallic_image_node = create_image_node(f"gltf_{config.PCB_name}_{material.name}_metallic", nodes, img_res)
    roughness_image_node = create_image_node(f"gltf_{config.PCB_name}_{material.name}_roughness", nodes, img_res)
    normal_image_node = create_image_node(f"gltf_{config.PCB_name}_{material.name}_normal", nodes, img_res)
    for node in nodes:
        if node.type == "OUTPUT_MATERIAL":
            mat_output_node = node
            continue
        if not hasattr(node, "node_tree"):
            continue
        if "Metallic_group" in node.node_tree.name:
            metallic_group_node = node
        elif "Color_group" in node.node_tree.name:
            color_group_node = node
        elif "Roughness_group" in node.node_tree.name:
            roughness_group_node = node

    # bake textures
    bake_texture(normal_image_node, nodes, "NORMAL")
    emission_node = nodes.new("ShaderNodeEmission")
    links.new(emission_node.outputs["Emission"], mat_output_node.inputs["Surface"])
    nodes_to_bake = [
        [color_group_node, color_image_node],
        [metallic_group_node, metallic_image_node],
        [roughness_group_node, roughness_image_node],
    ]
    for group, image in nodes_to_bake:
        links.new(group.outputs["Output_0"], emission_node.inputs["Color"])
        bake_texture(image, nodes, "EMIT")

    # load PCB template material
    load_materials(["gltf_main_pcb_template"])
    gltf_main_pcb_material = bpy.data.materials.get("gltf_main_pcb_template")
    gltf_main_pcb_material.name = f"gltf_{config.PCB_name}_{material.name}"
    gltf_nodes = gltf_main_pcb_material.node_tree.nodes

    # replace template textures with baked textures
    apply_baked_texture(gltf_nodes, "texture_color", color_image_node.image)  # type:ignore
    apply_baked_texture(gltf_nodes, "texture_metallic", metallic_image_node.image)  # type:ignore
    apply_baked_texture(gltf_nodes, "texture_roughness", roughness_image_node.image)  # type:ignore
    apply_baked_texture(gltf_nodes, "texture_normal", normal_image_node.image)  # type:ignore
    object_with_texture.select_set(False)
    return gltf_main_pcb_material


def convert_pcb_materials_to_gltf_format(board_col: bpy.types.Collection) -> None:
    """Bake PCB materials textures and update PCB materials to use them."""
    pcb_materials = ["main_pcb_top", "main_pcb_bot"]
    init_render_settings()
    f_cu_image = bpy.data.images["F_Cu.png"]
    img_resolution = f_cu_image.size
    for _, board_layer in enumerate(board_col.objects):
        for material_slot in board_layer.material_slots:
            material = material_slot.material
            if material.name not in pcb_materials:
                continue
            material_slot.material = make_gltf_compatibile_shader(board_layer, material, img_resolution)  # type:ignore
            bpy.data.materials.remove(material)
    cu.clear_obsolete_data()


def clear_and_set_solder_material(obj: bpy.types.Object) -> None:
    """Clear all materials and add solder material instead."""
    obj.data.materials.clear()  # type:ignore
    material = "gltf_Solder" if config.blendcfg["SETTINGS"]["GENERATE_GLTF"] else "Solder"
    load_materials([material])
    append_material(obj, material)
