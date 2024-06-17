"""Module generating 3D model of PCB based on supplied SVGs and PNGs."""

import bpy
import bmesh
import core.module
from typing import List, Tuple
import modules.config as config
import modules.stackup as stk
import modules.custom_utilities as cu
from modules.config import (
    GBR_IN,
    GBR_PTH,
    GBR_NPTH,
    GBR_EDGE_CUTS,
    GBR_F_CU,
    GBR_B_CU,
)
from os import listdir, path
from mathutils import Vector
from modules.materials import (
    process_materials,
    process_edge_materials,
    clear_empty_material_slots,
)
import logging
from typing import Optional, cast, Iterable

logger = logging.getLogger(__name__)


class Board(core.module.Module):
    """Board processing module."""

    def execute(self) -> None:
        """Execute Board module."""
        if path.isfile(config.pcb_blend_path) and not config.args.regenerate:
            logger.info(
                f"Board model already exists at {config.pcb_blend_path}. "
                "Not regenerating, as -r option was not specified"
            )
            return

        logger.info("Generating new PCB mesh.")
        make_board()
        cu.save_pcb_blend(config.pcb_blend_path, apply_transforms=True)


########################################


def make_board() -> bpy.types.Object:
    """Generate main board mesh."""
    logger.info("Generating board")

    in_list, layer_thickness = generate_inner_layer_list()
    logging.debug(f"Found layer list: {in_list}")
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
        config.pcbscale,
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
        config.pcbscale,
    )

    npth = prepare_mesh(
        "npth",
        config.svg_path + GBR_NPTH + ".svg",
        False,
        0.2,
        config.pcbscale,
    )

    offset_to_center = Vector(
        [
            cu.get_bbox(pcb, "centre")[0].x,
            cu.get_bbox(pcb, "centre")[0].y,
            0,
        ]
    )  # type: ignore

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
        logger.info("Cutting NPTH holes in board.")
        logger.warning("This operation may take a while!")
        boolean_diff(pcb, npth)
    # list of bare pcb edges vertices
    bare_pcb_verts = cu.get_vertices(pcb.data, 4)
    if pth:
        logger.info("Cutting PTH holes in board.")
        logger.warning("This operation may take a while!")
        boolean_diff(pcb, pth)
    all_pcb_verts = cu.get_vertices(pcb.data, 4)
    # list of plated pcb edges vertices
    plated_pcb_verts = cu.get_verts_difference(all_pcb_verts, bare_pcb_verts)  # type: ignore

    logger.debug(f"Number of verts on bare board edges: {len(bare_pcb_verts)}")
    logger.debug(f"Number of verts on plated board edges: {len(plated_pcb_verts)}")
    cu.remove_collection(f"{GBR_EDGE_CUTS}.svg")
    cu.remove_collection(f"{GBR_PTH}.svg")
    cu.remove_collection(f"{GBR_NPTH}.svg")

    # extrude board
    extrude_mesh(pcb, layer_thickness[0])
    cu.recalc_normals(pcb)

    map_pcb_to_uv(pcb)

    # add materials to board edges
    process_edge_materials(pcb, plated_pcb_verts, bare_pcb_verts)  # type: ignore

    if config.blendcfg["EFFECTS"]["STACKUP"]:
        logger.info("Creating layers (" + str(len(in_list)) + ")")
        for i in range(len(in_list)):
            pcb.select_set(True)
            # now original is selected
            bpy.ops.object.duplicate()
            # now duplicate is selected
            new_obj = bpy.context.selected_objects[0]  # type:ignore
            new_obj.name = "PCB_layer" + str(i + 2)
            logging.debug(f"Created layer {new_obj.name} at Z={sum(layer_thickness[0 : i + 1])}")
            cu.link_obj_to_collection(new_obj, board_col)
            new_obj.location += Vector((0, 0, sum(layer_thickness[0 : i + 1])))  # type: ignore
            bpy.ops.object.select_all(action="DESELECT")

    process_materials(board_col, in_list)

    # update layer thickness, done after process_materials
    # to keep set(pcb_verts).intersection(outline_verts) working
    for i, obj in enumerate(board_col.objects):
        for vert in obj.data.vertices:
            if vert.co[2] >= 0.0001:
                vert.co[2] = layer_thickness[i]

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

    # seperate layers
    thickness_sum = 0.0
    found_dielectric = 0
    sorted_layers = sorted(empty_obj.children, key=lambda x: int(x.name[9:]))  # type:ignore
    layers_count = len(sorted_layers)
    if config.blendcfg["EFFECTS"]["STACKUP"]:
        for layer, thick in stk.get().stackup_data[::-1]:
            if thick is None or found_dielectric > layers_count - 1:
                continue
            if "dielectric" in layer or "Mask" in layer:
                Vector(sorted_layers[found_dielectric].location).z += thickness_sum  # type:ignore
                found_dielectric += 1
            else:
                thickness_sum += thick

    project_col = cu.create_collection(config.PCB_name)
    for col in bpy.context.scene.collection.children:
        if col != project_col:
            bpy.context.scene.collection.children.unlink(col)
            project_col.children.link(col)

    clear_empty_material_slots()

    logger.info("Board generated!")
    return empty_obj


def generate_inner_layer_list() -> Tuple[List[str], List[float]]:
    """Generate a list of inner layer PNGs that need to be included in the model.

    Additionally, returns the thickness of each layer.
    """
    in_list: List[str] = []
    all_layer_thickness = [stk.get().thickness]

    # When stackup generation is disabled, don't need to do anything else
    if not config.blendcfg["EFFECTS"]["STACKUP"]:
        return in_list, all_layer_thickness

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
    if not stk_data:
        # When no stackup data is provided, divide the configured PCB thickness evenly
        all_layer_thickness = [stk.get().thickness / (len(all_list) + 1) for _ in range(len(all_list) + 1)]
    else:
        # Find the thickness of "dielectric <N>" entries in the stackup and sort
        # based on their names. This is used as the thickness of the inner layers.
        stk_in_list = [pair[0] for pair in stk_data if GBR_IN in pair[0]]
        if len(in_list) != len(stk_in_list):
            raise RuntimeError(
                f"Stackup layer mismatch between exported gerber files and stackup.json\n"
                f"Found {len(in_list)} gerber file(s), found {len(stk_in_list)} layer(s) defined in JSON. Aborting!"
            )
        in_layer_thickness = [
            pair[1]
            for pair in sorted(
                list(filter(lambda pair: "dielectric" in pair[0], stk_data)),
                reverse=True,
            )
        ]
        # Sandwich the inner layers between thicknesses for Back and Front mask
        all_layer_thickness = (
            [pair[1] for pair in stk_data if "B.Mask" in pair[0]]
            + in_layer_thickness
            + [pair[1] for pair in stk_data if "F.Mask" in pair[0]]
        )

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


def map_pcb_to_uv(pcb: bpy.types.Object) -> None:
    """PCB surfaces UV mapping function."""
    area3d = get_area_by_type("VIEW_3D")
    if area3d is None:
        return
    for ns3d in area3d.spaces:
        if ns3d.type == "VIEW_3D":
            break
    assert isinstance(ns3d, bpy.types.SpaceView3D)
    win = bpy.context.window
    scr = win.screen
    region = [region for region in area3d.regions if region.type == "WINDOW"]

    override = {
        "window": win,
        "screen": scr,
        "area": get_area_by_type("VIEW_3D"),
        "region": region[0],
        "scene": bpy.context.scene,
        "space": ns3d,
    }

    if ns3d.region_3d.view_perspective == "PERSP":
        bpy.ops.view3d.view_persportho(override)

    cu.face_sel(pcb, "top")
    bpy.ops.uv.cube_project(
        override,
        cube_size=1.0,
        correct_aspect=True,
        clip_to_bounds=True,
        scale_to_bounds=True,
    )

    cu.face_sel(pcb, "bot")
    bpy.ops.uv.cube_project(
        override,
        cube_size=1.0,
        correct_aspect=True,
        clip_to_bounds=True,
        scale_to_bounds=True,
    )
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.view3d.view_persportho(override)


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
    # apply the modifier
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier=bool_modifier.name)
    # delete tool object
    bpy.data.objects[tool.name].select_set(True)
    bpy.ops.object.delete()
    bpy.ops.object.select_all(action="DESELECT")
    clean_bool_diff_artifacts(obj)


def clean_outline(mesh: bpy.types.Object) -> None:
    """Import outline from edgecuts."""
    bpy.context.view_layer.objects.active = mesh
    mesh.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles()
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


def import_svg(name: str, filepth: str) -> Optional[bpy.types.Object]:
    """Import curve from SVG vector file."""
    if not path.exists(filepth):
        return None
    return_obj = None
    svgname = filepth.split("/")[-1]
    bpy.ops.import_curve.svg(filepath=str(filepth))
    for obj in bpy.data.collections[svgname].all_objects:
        bpy.context.view_layer.objects.active = obj
        obj.select_set(True)
    curve_count = len(bpy.context.selected_objects)  # type:ignore
    logger.info("Importing SVG from " + svgname + " (curve count: " + str(curve_count) + ")")
    if curve_count != 0:
        bpy.ops.object.convert(target="MESH")
        bpy.ops.object.join()
        new_obj = bpy.context.selected_objects[0]  # type:ignore
        new_obj.name = name
        return_obj = new_obj
    return return_obj


def prepare_mesh(name: str, svg_path: str, clean: bool, height: float, scale: float) -> Optional[bpy.types.Object]:
    """Prepare mesh from imported curve."""
    bpy.ops.object.select_all(action="DESELECT")
    obj: bpy.types.Object | None = import_svg(name, svg_path)
    if obj is not None:
        if clean:
            clean_outline(obj)
        obj.scale = scale * Vector(obj.scale)  # type: ignore
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
        extrude_mesh(obj, height)
        obj.data.name = name + "_mesh"
        logger.info("Mesh for " + name + " created.")
    else:
        logger.warning("No mesh created for " + name + ".")
        return None
    return obj


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
