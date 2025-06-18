"""Module generating 3D model of PCB based on supplied SVGs and PNGs."""

import bmesh
import bpy
import logging

from mathutils import Vector
from os import listdir, path
from typing import List, Tuple, Optional, cast, Iterable, Literal

import gerber2blend.core.module
import gerber2blend.modules.config as config
import gerber2blend.modules.custom_utilities as cu
import gerber2blend.modules.stackup as stk

from gerber2blend.modules.config import (
    GBR_IN,
    GBR_PTH,
    GBR_NPTH,
    GBR_EDGE_CUTS,
    GBR_F_CU,
    GBR_B_CU,
    OUT_F_SOLDER,
    OUT_B_SOLDER,
)
from gerber2blend.modules.materials import (
    process_materials,
    process_edge_materials,
    clear_and_set_solder_material,
)


logger = logging.getLogger(__name__)


class Board(gerber2blend.core.module.Module):
    """Board processing module."""

    def execute(self) -> None:
        """Execute Board module."""
        if path.isfile(config.pcb_blend_path) and not config.args.regenerate:
            logger.info(f"Board model already exists at {config.pcb_blend_path}. ")
            logger.info("Exiting Board module. Run with -r to regenerate the model.")
            return
        logger.info("Generating new PCB mesh.")
        make_board()
        config.board_created = True
        cu.save_pcb_blend(config.pcb_blend_path, apply_transforms=True)
        if config.blendcfg["SETTINGS"]["GENERATE_GLTF"]:
            prepare_gltf_structure()
            cu.save_pcb_blend(config.pcb_blend_path, apply_transforms=True)
            bpy.ops.wm.open_mainfile(filepath=config.pcb_blend_path)
            cu.export_to_gltf(config.pcb_gltf_file_path)
            if config.blendcfg["SETTINGS"]["TEXTURES_FORMAT"] == "KTX2":
                cu.convert_ktx2(config.pcb_gltf_file_path)


########################################


def make_board() -> bpy.types.Object:
    """Generate main board mesh."""
    logger.info("Generating board")

    all_list, layer_thickness = generate_all_layers_list()
    logging.debug(f"Found layer list: {all_list}")
    logging.debug(f"Thickness of layers: {layer_thickness}")
    board_col = cu.create_collection("Board")

    # preparing empty parent object with verticies of PCB bbox
    bbox_mesh = bpy.data.meshes.new("PCB_BBOX")
    empty_obj = bpy.data.objects.new(config.PCB_name, bbox_mesh)

    # preparing meshes for outline and holes
    pcb: bpy.types.Object | None = prepare_mesh(
        "PCB_layer1",
        config.svg_path + GBR_EDGE_CUTS + ".svg",
        True,
        0.0,
        config.pcbscale_gerbv,
    )
    if pcb is None:
        return empty_obj
    assert isinstance(pcb.data, bpy.types.Mesh)
    cu.link_obj_to_collection(pcb, board_col)
    cu.recalc_normals(pcb)

    pth = prepare_mesh(
        "pth",
        config.svg_path + GBR_PTH + ".svg",
        False,
        0.2,
        config.pcbscale_gerbv,
    )

    npth = prepare_mesh(
        "npth",
        config.svg_path + GBR_NPTH + ".svg",
        False,
        0.2,
        config.pcbscale_gerbv,
    )

    offset_to_center = Vector(
        [
            cu.get_bbox(pcb, "centre")[0].x,
            cu.get_bbox(pcb, "centre")[0].y,
            0,
        ]
    )  # type: ignore

    if config.blendcfg["EFFECTS"]["SOLDER"]:
        solder_top = prepare_solder(OUT_F_SOLDER, config.pcbscale_vtracer)
        if solder_top is not None:
            solder_top.location[0] -= pcb.dimensions[0] / 2
            solder_top.location[1] += pcb.dimensions[1] / 2
            solder_top.location[2] += sum(layer_thickness)
            solder_top.select_set(True)
            bpy.context.view_layer.objects.active = solder_top
            bpy.ops.object.transform_apply()

        solder_bot = prepare_solder(OUT_B_SOLDER, config.pcbscale_vtracer)
        if solder_bot is not None:
            bpy.ops.object.select_all(action="DESELECT")
            solder_bot.location[0] -= pcb.dimensions[0] / 2
            solder_bot.location[1] += pcb.dimensions[1] / 2
            solder_bot.select_set(True)
            bpy.context.view_layer.objects.active = solder_bot
            bpy.ops.transform.resize(value=(1.0, 1.0, -1.0))
            bpy.ops.object.transform_apply()
            solder_bot.select_set(True)

        if solder_top is not None:
            bpy.context.view_layer.objects.active = solder_top
            solder_top.select_set(True)
        if not bpy.context.selected_objects:
            # both top and bottom solder are empty
            config.blendcfg["EFFECTS"]["SOLDER"] = False
        else:
            bpy.ops.object.join()
            solder = bpy.context.selected_objects[0]  # type:ignore
            solder.name = "Solder"
            bpy.ops.object.shade_smooth()
            bpy.ops.object.select_all(action="DESELECT")
            clear_and_set_solder_material(solder)

        for obj in bpy.context.scene.objects:
            cu.apply_all_transform_obj(obj)

    # move pcb and holes to center; move holes below Z
    pcb.location -= offset_to_center  # type:ignore
    if pth:
        pth.location -= offset_to_center  # type:ignore
        pth.location += Vector([0, 0, -0.1])  # type: ignore
    if npth:
        npth.location -= offset_to_center  # type:ignore
        npth.location += Vector([0, 0, -0.1])  # type: ignore

    # put origin point in the middle of PCB
    pcb.select_set(True)
    bpy.context.view_layer.objects.active = pcb
    bpy.ops.object.transform_apply(
        location=True,
        rotation=False,
        scale=False,
        properties=False,
        isolate_users=False,
    )
    pcb.select_set(False)

    # holes boolean diff
    if npth:
        logger.info("Cutting NPTH holes in board (may take a while!).")
        boolean_diff(pcb, npth)
    # list of bare pcb edges vertices
    bare_pcb_verts = cu.get_vertices(pcb.data, 4)
    if pth:
        logger.info("Cutting PTH holes in board (may take a while!).")
        boolean_diff(pcb, pth)

    all_pcb_verts = cu.get_vertices(pcb.data, 4)
    # list of plated pcb edges vertices
    plated_pcb_verts = cu.get_verts_difference(all_pcb_verts, bare_pcb_verts)  # type: ignore

    logger.debug(f"Number of verts on bare board edges: {len(bare_pcb_verts)}")
    logger.debug(f"Number of verts on plated board edges: {len(plated_pcb_verts)}")
    # extrude board
    extrude_mesh(pcb, layer_thickness[0])
    cu.recalc_normals(pcb)
    cu.make_sharp_edges(pcb)

    map_pcb_to_uv(pcb, all_pcb_verts)

    # add materials to board edges
    process_edge_materials(pcb, plated_pcb_verts, bare_pcb_verts)  # type: ignore
    if config.blendcfg["EFFECTS"]["STACKUP"]:
        logger.info("Creating layers (" + str(len(all_list)) + ")")
        z_counter = layer_thickness[0]
        for i in range(len(all_list)):
            pcb.select_set(True)
            # now original is selected
            bpy.ops.object.duplicate()
            # now duplicate is selected
            new_obj = bpy.context.selected_objects[0]  # type:ignore
            new_obj.name = "PCB_layer" + str(i + 2)
            layer_width = layer_thickness[i + 1]
            logging.debug(f"Created layer {new_obj.name} at Z={z_counter:.3f} with width={layer_width:.3f}")
            cu.link_obj_to_collection(new_obj, board_col)
            # update layer thickness
            for vert in new_obj.data.vertices:  # type: ignore
                if vert.co[2] >= 0.0001:
                    vert.co[2] = layer_width
            # move layer up
            new_obj.location.z = z_counter  # type: ignore
            z_counter += layer_width
            bpy.ops.object.select_all(action="DESELECT")

    process_materials(board_col, all_list)

    if config.blendcfg["EFFECTS"]["SOLDER"]:
        cu.link_obj_to_collection(solder, board_col)

    # board measurements
    logger.info(
        "Board dimensions: x:"
        + str(Vector(pcb.dimensions).x)  # type: ignore
        + " y:"
        + str(Vector(pcb.dimensions).y)  # type: ignore
        + " z:"
        + str(stk.get().thickness)
    )

    # parent to empty object (pcb_parent)
    bpy.ops.object.select_all(action="DESELECT")
    cu.link_obj_to_collection(empty_obj, board_col)
    for obj in board_col.objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = empty_obj  # active obj will be parent
    bpy.ops.object.parent_set(keep_transform=True)
    bpy.ops.object.select_all(action="DESELECT")

    # add vertices to empty object to store BBOX of PCB (dimensions)
    bbox_mesh.vertices.add(8)
    for i, vert in enumerate(cu.get_bbox(pcb, "3d")):
        bbox_mesh.vertices[i].co = vert.copy()
        if bbox_mesh.vertices[i].co[2] >= 0.0001:
            bbox_mesh.vertices[i].co[2] = stk.get().thickness

    project_col = cu.create_collection(config.PCB_name)
    for col in bpy.context.scene.collection.children:
        if col != project_col:
            bpy.context.scene.collection.children.unlink(col)
            project_col.children.link(col)

    cu.clear_obsolete_data()
    logger.info("Board generated!")
    return empty_obj


def generate_all_layers_list() -> Tuple[List[str], List[float]]:
    """Generate a list of all layer PNGs that need to be included in the model.

    Additionally, returns the thickness of each layer.
    """
    all_list: List[str] = []
    all_layer_thickness = [stk.get().thickness]

    # When stackup generation is disabled, don't need to do anything else
    if not config.blendcfg["EFFECTS"]["STACKUP"]:
        return all_list, all_layer_thickness

    # Collect all inner layer PNG files from the fabrication data folder
    in_list = sorted(
        list(
            filter(
                lambda f: f.startswith(GBR_IN) and f.endswith(".png"),
                listdir(config.png_path),
            )
        ),
        key=lambda x: int(x[len(GBR_IN) :].replace(".png", "")),
        reverse=True,
    )
    if len(in_list) == 0:
        logger.warning(
            f"Could not find any converted inner layer PNGs in {config.png_path}!\n"
            f"Verify if the inner layer gerbers are present and specified "
            f"with GERBER_FILENAMES in the blendcfg.yaml file."
        )
    # Sandwich the inner layers between Back and Front Cu
    all_list = [f"{GBR_B_CU}.png"] + in_list + [f"{GBR_F_CU}.png"]
    stk_data = stk.get().stackup_data
    layer_count = len(all_list) + 1
    if not stk_data:
        # When no stackup data is provided, divide the configured PCB thickness evenly
        all_layer_thickness = [stk.get().thickness / layer_count] * layer_count
    else:
        # Find the thickness of "dielectric <N>" entries in the stackup and sort
        # based on their names. This is used as the thickness of the inner layers.
        stk_in_list = [entry["name"] for entry in stk_data if GBR_IN in entry["name"]]
        if len(in_list) != len(stk_in_list):
            raise RuntimeError(
                f"Stackup layer mismatch between exported gerber files and stackup.json\n"
                f"Found {len(in_list)} gerber file(s), found {len(stk_in_list)} layer(s) defined in JSON. Aborting!"
            )
        in_layer_thickness = [entry["thickness"] for entry in stk_data if "dielectric" in entry["name"]]
        cu_layer_thickness = [entry["thickness"] for entry in stk_data if ".Cu" in entry["name"]]
        sum_cu = sum(cu_layer_thickness)
        in_layer_thickness.reverse()
        front_thickness = [
            sum(
                [
                    entry["thickness"]
                    for entry in stk_data
                    if isinstance(entry["thickness"], float)
                    and entry["name"].startswith("F.")
                    and not entry["name"].endswith(".Cu")
                ]
            )
        ]
        back_thickness = [
            sum(
                [
                    entry["thickness"]
                    for entry in stk_data
                    if isinstance(entry["thickness"], float)
                    and entry["name"].startswith("B.")
                    and not entry["name"].endswith(".Cu")
                ]
            )
        ]
        # Sandwich the inner layers between thicknesses for Back and Front mask
        all_layer_thickness = back_thickness + in_layer_thickness + front_thickness
        for i, _val in enumerate(all_layer_thickness):
            all_layer_thickness[i] += sum_cu / layer_count

    return all_list, all_layer_thickness


########################################
# board UV mapping


def get_area_by_type(area_type: str) -> Optional[bpy.types.Area]:
    """Get area for context override."""
    for screen in bpy.context.workspace.screens:
        for area in screen.areas:
            if area.type == area_type:
                return area
    return None


def map_faces_to_uv(
    pcb: bpy.types.Object, side: Literal["top", "bot", "edge"], pcb_verts: None | list[Tuple[float]] = None
) -> None:
    """Map specified PCB side to UV."""
    cu.face_desel(pcb)
    cu.face_sel(pcb, side, pcb_verts)
    bpy.ops.uv.cube_project(
        cube_size=1.0,
        correct_aspect=True,
        clip_to_bounds=True,
        scale_to_bounds=True,
    )


def map_pcb_to_uv(pcb: bpy.types.Object, pcb_verts: list[Tuple[float]]) -> None:
    """PCB surfaces UV mapping function."""
    map_faces_to_uv(pcb, "top")
    map_faces_to_uv(pcb, "bot")
    map_faces_to_uv(pcb, "edge", pcb_verts)
    bpy.ops.object.mode_set(mode="OBJECT")


########################################
# board generation


def boolean_diff(obj: bpy.types.Object, tool: bpy.types.Object) -> None:
    """Apply boolean diff modifier on object and remove the tool and artifacts afterwards."""
    # define boolean operation
    bool_modifier = obj.modifiers.new(name="diff", type="BOOLEAN")
    assert isinstance(bool_modifier, bpy.types.BooleanModifier)
    bool_modifier.operation = "DIFFERENCE"
    # set tool objects
    bool_modifier.object = tool
    bool_modifier.use_hole_tolerant = True

    # apply the modifier
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bool_modifier.name)
    # delete tool object
    bpy.data.objects[tool.name].select_set(True)
    bpy.ops.object.delete()
    bpy.ops.object.select_all(action="DESELECT")
    clean_bool_diff_artifacts(obj)


def boolean_intersect(obj: bpy.types.Object, tool: bpy.types.Object) -> None:
    """Apply boolean intersect modifier on object and remove the tool afterwards."""
    # define boolean operation
    bpy.ops.object.select_all(action="DESELECT")
    bool_modifier = obj.modifiers.new(name="intersect", type="BOOLEAN")
    assert isinstance(bool_modifier, bpy.types.BooleanModifier)
    bool_modifier.operation = "INTERSECT"
    # set tool objects
    bool_modifier.object = tool
    # apply the modifier
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bool_modifier.name)
    # delete tool object
    bpy.ops.object.select_all(action="DESELECT")
    bpy.data.objects[tool.name].select_set(True)
    bpy.ops.object.delete()
    bpy.ops.object.select_all(action="DESELECT")


def clean_outline(mesh: bpy.types.Object) -> None:
    """Import outline from edgecuts."""
    bpy.context.view_layer.objects.active = mesh
    mesh.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.005)
    bpy.ops.mesh.fill()
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")


def extrude_mesh(obj: bpy.types.Object, height: float) -> None:
    """Extrude flat mesh using specified height."""
    if height > 0.0:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0, 0, height)})
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.select_all(action="DESELECT")


def import_svg(
    name: str, filepth: str, scale: float, join: bool = True
) -> Optional[bpy.types.Object | bpy.types.Collection]:
    """Import curve from SVG vector file."""
    if not path.exists(filepth):
        return None
    svgname = filepth.split("/")[-1]
    bpy.ops.import_curve.svg(filepath=str(filepth))
    col = bpy.data.collections[svgname]
    for obj in col.all_objects:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
    curve_count = len(bpy.context.selected_objects)  # type:ignore
    logger.info("Importing SVG from " + svgname + " (curve count: " + str(curve_count) + ")")
    if curve_count != 0:
        bpy.ops.object.convert(target="MESH")
        bpy.ops.transform.resize(value=(scale, scale, scale))  # type: ignore
        if join:
            bpy.ops.object.join()
            new_obj = bpy.context.selected_objects[0]  # type:ignore
            new_obj.name = name

            bpy.ops.object.mode_set(mode="EDIT")
            bpy.ops.mesh.select_all(action="SELECT")
            bpy.ops.mesh.dissolve_limited()
            bpy.ops.object.mode_set(mode="OBJECT")
            return new_obj
        col.name = name
        return col
    return None


def prepare_mesh(name: str, svg_path: str, clean: bool, height: float, scale: float) -> Optional[bpy.types.Object]:
    """Prepare mesh from imported curve."""
    bpy.ops.object.select_all(action="DESELECT")
    obj = import_svg(name, svg_path, scale)
    if isinstance(obj, bpy.types.Object):
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.transform_apply(
            location=False,
            rotation=False,
            scale=True,
            properties=False,
            isolate_users=False,
        )
        obj.select_set(False)
        if clean:
            clean_outline(obj)
        extrude_mesh(obj, height)
        obj.data.name = name + "_mesh"
        logger.info("Mesh for " + name + " created.")
    else:
        logger.warning("No mesh created for " + name + ".")
        return None
    return obj


def solder_single(obj: bpy.types.Object) -> None:
    """Extrude Solder mesh for single pad."""
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    size = obj.dimensions

    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.fill_holes(sides=0)
    bpy.ops.mesh.dissolve_limited()

    mindim = size[0] if size[0] < size[1] else size[1]
    if mindim < 0.4:
        steps = [(0.07, 0.5)]
    elif mindim < 0.8:
        steps = [(0.1, 0.5)]
    elif mindim < 1.2:
        steps = [(0.1, 0.8), (0.1, 0.5)]
    else:
        steps = [(0.1, 1 - 0.3 / mindim), (0.1, 1 - 0.4 / mindim), (0.19, 0.4)]

    for height, scale in steps:
        bpy.ops.mesh.extrude_region_move(TRANSFORM_OT_translate={"value": (0, 0, height)})
        bpy.ops.transform.resize(value=(scale, scale, 1.0))  # type: ignore

    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")


def prepare_solder(base_name: str, scale: float) -> Optional[bpy.types.Object]:
    """Prepare Solder mesh for single board side."""
    input_file = config.svg_path + base_name + ".svg"
    input_file_fixer = config.svg_path + base_name + "_fixer.svg"
    bpy.ops.object.select_all(action="DESELECT")

    col = import_svg(base_name, input_file, scale, False)
    if isinstance(col, bpy.types.Collection):
        logger.info(f"Generating {base_name} mesh (may take a while!).")
        bpy.ops.object.select_all(action="DESELECT")
        for obj in col.objects:
            solder_single(obj)

        for obj in col.objects:
            obj.select_set(True)
        bpy.ops.object.join()
        new_obj = bpy.context.selected_objects[0]  # type:ignore
        new_obj.name = base_name
        new_obj.data.name = base_name + "_mesh"
        logger.info("Mesh for " + base_name + " created.")
        fixer = prepare_mesh(base_name + "_fixer", input_file_fixer, False, 1, scale)
        if fixer is not None:
            fixer.location[2] -= 0.2
            boolean_intersect(new_obj, fixer)
            logger.info("Excessive soldering corrected")
        return new_obj
    return None


def clean_bool_diff_artifacts(pcb: bpy.types.Object) -> None:
    """Remove vertices that are not on Z=0 (those vertices are created by corrupted boolean diff operation)."""
    bpy.ops.object.mode_set(mode="EDIT")
    assert isinstance(pcb.data, bpy.types.Mesh)
    mesh_obj = bmesh.from_edit_mesh(pcb.data)
    logging.debug(f"Initial count of vertices in mesh: {len(mesh_obj.verts)}")  # type:ignore
    verts = [v for v in cast(Iterable[bmesh.types.BMVert], mesh_obj.verts) if abs(float(v.co[2])) > 0]
    bmesh.ops.delete(mesh_obj, geom=verts, context="VERTS")
    bmesh.update_edit_mesh(pcb.data)
    logging.debug(f"Number of corrupted vertices to remove: {len(verts)}")
    logging.debug(f"Final count of vertices in mesh: {len(mesh_obj.verts)}")  # type:ignore
    bpy.ops.object.mode_set(mode="OBJECT")


def prepare_gltf_structure() -> None:
    """Prepare structure and data for glTF export."""
    cu.mkdir(config.pcb_gltf_dir_path)
    obj = bpy.data.objects.get(config.PCB_name)
    # save PCB dimensions in glTF
    obj["PCB_X"] = obj.dimensions.x
    obj["PCB_Y"] = obj.dimensions.y
    obj["PCB_Z"] = obj.dimensions.z
