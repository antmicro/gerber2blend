"""Module containing custom utilities functions."""

import bpy
import bmesh
import math
from mathutils import Vector, kdtree
import logging
from typing import List, Tuple, Any, Literal
import os
import re
import subprocess
from pygltflib import GLTF2  # type:ignore
from pathlib import Path
import gerber2blend.modules.config as config
import shutil

logger = logging.getLogger(__name__)


def get_vertices(mesh: bpy.types.Mesh, precision: int = 0) -> List[Tuple[float]]:
    """Return list of object's vertices with float precision =-1."""
    verts = [vert.co for vert in mesh.vertices]
    return [Vector(vert).to_tuple(precision) for vert in verts]  # type: ignore


def make_kd_tree(verts: List[Tuple[float]]) -> kdtree.KDTree:
    """Return K-D tree of model vertices."""
    main_list = list(verts)
    kd = kdtree.KDTree(len(main_list))  # type: ignore
    for i, v in enumerate(main_list):
        kd.insert(v, i)
    kd.balance()  # type: ignore
    return kd


def get_verts_difference(main_set: List[Tuple[float]], remove_set: List[Tuple[float]]) -> List[Tuple[float]]:
    """Remove set of vertices from another set."""
    main_list = list(main_set)
    kd = make_kd_tree(main_list)
    indexes_to_remove = []
    for vert in remove_set:
        _, index, dist = kd.find(vert)
        if dist < 0.0001 and index not in indexes_to_remove:  # points in the same place
            indexes_to_remove.append(index)

    for index in sorted(indexes_to_remove, reverse=True):
        main_list.pop(index)
    return main_list


def verts_in(kd: kdtree.KDTree, add_set: List[Vector]) -> bool:
    """Check if there are common vertices for two sets (using previously created kdtree)."""
    for vert in add_set:
        *_, dist = kd.find(vert)
        if dist:
            if dist < 0.0001:  # points in the same place
                return True
    return False


def get_bbox(obj: bpy.types.Object, arg: str) -> list[Any | Vector]:
    """Get bbox of an object.

    Args:
    ----
    obj:
        object which bounding box must be found
    arg:
        'centre' - finds current center point of the model
        '2d' - finds 2D bounding box of projection
        '3d' - finds 3D bounding box

    """
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    bbox_vert = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]  # type:ignore
    if arg == "centre":
        centre = sum(bbox_vert, Vector())  # type:ignore
        centre /= 8
        return [centre]
    if arg == "2d":
        corner2d = [corner.to_2d() for corner in bbox_vert]
        return corner2d[::2]
    if arg == "3d":
        return bbox_vert
    raise RuntimeError("Incorrect bbox input argument")


def recalc_normals(obj: bpy.types.Object) -> None:
    """Recalculate normals in object."""
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")


def make_sharp_edges(obj: bpy.types.Object) -> None:
    """Set edges on PCB as 'sharp edges' to properly visualize shaders.

    Will work only for edges connecting exactly two faces and angle between those faces in [85,95]deg range
    """
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="DESELECT")
    bm = bmesh.from_edit_mesh(obj.data)  # type: ignore
    for edge in bm.edges:
        if len(edge.link_faces) == 2:
            face_angle_deg = math.degrees(edge.calc_face_angle())
            if abs(90 - face_angle_deg) < 5:
                edge.select_set(True)
    bpy.ops.mesh.mark_sharp()
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")


def face_sel(
    obj: bpy.types.Object, pos: Literal["top", "bot", "edge"], edge_verts: None | List[Tuple[float]] = None
) -> None:
    """Select faces facing specified direction (top, bottom, edge)."""
    if edge_verts is None:
        edge_verts = []
    bpy.context.view_layer.objects.active = obj
    assert isinstance(obj.data, bpy.types.Mesh)
    mesh = obj.data
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()  # type: ignore
    kd = make_kd_tree(edge_verts)
    for face in obj.data.polygons:  # type: ignore
        if pos == "edge":
            # check vertical faces
            if abs(Vector(face.normal).z) <= 0.5:  # type: ignore
                # check if face contains vertices from list
                face_edges = []
                for ind in face.vertices:
                    face_edges.append(obj.data.vertices[ind].co)
                if verts_in(kd, face_edges):  # type: ignore
                    bm.faces[face.index].select = True
        elif pos == "top":
            bm.faces[face.index].select = Vector(face.normal).z > 0.5  # type: ignore
        elif pos == "bot":
            bm.faces[face.index].select = Vector(face.normal).z < -0.5  # type: ignore
        else:
            logger.error("Specify pos")
    bmesh.update_edit_mesh(mesh)  # type: ignore


def face_desel(obj: bpy.types.Object) -> None:
    """Deselect all faces."""
    mesh = obj.data
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(mesh)  # type: ignore
    bm.faces.ensure_lookup_table()  # type: ignore
    for face in obj.data.polygons:  # type: ignore
        bm.faces[face.index].select = False


def create_collection(name: str) -> Any:
    """Create and link objects to collection."""
    if not bpy.data.collections.get(name):
        new_col = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(new_col)
    return bpy.data.collections.get(name)


def remove_collection(name: str) -> None:
    """Remove collection."""
    rem_col = bpy.context.scene.collection.children.get(name)
    if rem_col is not None:
        bpy.data.collections.remove(rem_col)


def link_obj_to_collection(obj: bpy.types.Object, target_coll: bpy.types.Collection) -> None:
    """Loop through all collections the obj is linked to and unlink it from there, then link to targed collection."""
    for coll in obj.users_collection:  # type: ignore
        coll.objects.unlink(obj)
    target_coll.objects.link(obj)


def apply_all_transform_obj(obj: bpy.types.Object) -> None:
    """Apply all object transformations."""
    obj.select_set(True)
    bpy.ops.object.transform_apply()
    obj.select_set(False)


def make_image_paths_relative(image: bpy.types.Image) -> None:
    """Set image paths to relative."""
    image.filepath = f"//{image.filepath.split('/')[-1]}"
    for packed_image in image.packed_files:
        packed_image.filepath = f"//{packed_image.filepath.split('/')[-1]}"


def mkdir(path: str) -> None:
    """Create a directory at the specified path.

    Wraps any errors with a nicer error exception.
    """
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Could not create folder at path {path}: {repr(e)}") from e


def strip_prefix_from_textures(files_path: Path, gltf_imgs: List[Any], prefix: str) -> None:
    """Strip glTF textures from prefix in name."""
    for file in files_path.iterdir():
        file.replace(file.with_stem(file.stem.replace(prefix, "")))
    for img in gltf_imgs:
        img.name = img.name.replace(prefix, "")
        img.uri = img.uri.replace(prefix, "")


def export_to_gltf(gltf_file_str: str) -> None:
    """Save PCB in glTF format."""
    gltf_file_path = Path(gltf_file_str)
    gltf_dir = gltf_file_path.parent
    logger.info(f"Exporting PCB model into glTF format to: {str(gltf_file_path)}")
    bpy.ops.export_scene.gltf(
        filepath=str(gltf_file_path),
        check_existing=False,
        export_format="GLTF_SEPARATE",
        export_extras=True,
        export_apply=True,
        export_texture_dir=str(gltf_dir),
        export_draco_mesh_compression_enable=True,
    )
    gltf = GLTF2().load(gltf_file_path)
    gltf_images = gltf.images
    strip_prefix_from_textures(gltf_dir, gltf_images, prefix="gltf_")
    pattern = re.compile(r"([A-Za-z0-9-_]+)_metallic-\1_roughness")
    for img in gltf_images:
        if not (match := pattern.match(img.name)):
            continue
        new_name = f"{match.group(1)}_metallic_roughness"
        img_file = gltf_dir / img.uri
        img_file.rename(gltf_dir / f"{new_name}{img_file.suffix}")
        img.uri = img.uri.replace(img.name, new_name)
        img.name = new_name
    gltf.save(gltf_file_path)


def convert_ktx2(gltf_file_str: str) -> None:
    """Convert glTF textures to .ktx2 format."""
    gltf_file_path = Path(gltf_file_str)
    gltf_dir = gltf_file_path.parent
    logger.info("Converting glTF textures to .ktx2 format.")
    npm_use_cmd = "export NVM_DIR=$HOME/.nvm && source $NVM_DIR/nvm.sh && nvm use 22 >/dev/null"
    transform_log = subprocess.run(
        f"{npm_use_cmd} && gltf-transform -V", shell=True, executable="/bin/bash", text=True, capture_output=True
    )
    if transform_log.stdout.strip() != "4.2.0":
        logger.error(transform_log)
        raise RuntimeError("gltf-transform CLI not found or in wrong version. Install it with `npm install -g`.")
    subprocess.run(
        f"{npm_use_cmd} && gltf-transform uastc {str(gltf_file_path)} {str(gltf_file_path)}",
        shell=True,
        executable="/bin/bash",
        text=True,
    )
    for texture_path in gltf_dir.iterdir():
        if texture_path.suffix == ".png":
            texture_path.unlink()


def save_pcb_blend(path: str, apply_transforms: bool = False) -> None:
    """Save blendfile."""
    bpy.ops.file.pack_all()
    if apply_transforms:
        for obj in bpy.context.scene.objects:
            apply_all_transform_obj(obj)
    bpy.ops.wm.save_as_mainfile(filepath=path)


def clear_obsolete_data() -> None:
    """Cleanup obsolete data from file."""
    clear_unused_meshes()
    clear_unused_curves()
    clear_empty_material_slots()
    clear_unused_materials()
    clear_unused_images()
    remove_empty_collections()


def clear_unused_meshes() -> None:
    """Remove unused meshes from file."""
    for mesh in bpy.data.meshes:
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)


def clear_unused_curves() -> None:
    """Remove unused curves from file."""
    for curve in bpy.data.curves:
        if curve.users == 0:
            bpy.data.curves.remove(curve)


def clear_unused_images() -> None:
    """Remove unused images from file."""
    for image in bpy.data.images:
        if image.users == 0:
            bpy.data.images.remove(image)


def clear_unused_materials() -> None:
    """Remove unused materials from file."""
    for mat in bpy.data.materials:
        if mat.users == 0 or mat.name == "Dots Stroke":
            bpy.data.materials.remove(mat)


def clear_empty_material_slots() -> None:
    """Clear empty slots in all objects on scene."""
    for obj in bpy.data.collections["Board"].all_objects:
        bpy.context.view_layer.objects.active = obj
        for slot in obj.material_slots:
            if not slot.material:
                bpy.context.object.active_material_index = slot.slot_index
                bpy.ops.object.material_slot_remove()


def remove_empty_collections() -> None:
    """Remove all collections with no children."""
    for col in bpy.data.collections:
        if not col.all_objects:
            bpy.data.collections.remove(col)
