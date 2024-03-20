import bpy  # type: ignore
import bmesh  # type: ignore
from mathutils import Vector, kdtree  # type: ignore
import logging

logger = logging.getLogger(__name__)


def get_vertices(obj, precision=0):
    """Return list of object's vertices with float precision =-1"""

    verts = [vert.co for vert in obj.data.vertices]
    plain_verts = [vert.to_tuple(precision) for vert in verts]
    return plain_verts


def make_kd_tree(verts):
    """Return K-D tree of model vertices"""

    main_list = list(verts)
    kd = kdtree.KDTree(len(main_list))
    for i, v in enumerate(main_list):
        kd.insert(v, i)
    kd.balance()
    return kd


def get_verts_difference(main_set, remove_set):
    """Remove set of vertices from another set"""

    main_list = list(main_set)
    kd = make_kd_tree(main_list)
    indexes_to_remove = []
    for vert in remove_set:
        _, index, dist = kd.find(vert)
        if dist < 0.0001:  # points in the same place
            indexes_to_remove.append(index)

    for id in sorted(indexes_to_remove, reverse=True):
        main_list.pop(id)
    return main_list


def verts_in(kd, add_set):
    """Check if there are common vertices for two sets (using previously created kdtree)"""

    for vert in add_set:
        *_, dist = kd.find(vert)
        if dist:
            if dist < 0.0001:  # points in the same place
                return True
    return False


def get_bbox(obj, arg):
    """Gets bbox of an object
    Arguments:
    'centre' - finds current center point of the model
    '2d' - finds 2D bounding box of projection
    '3d' - finds 3D bounding box
    """

    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = obj
    bbox_vert = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    if arg == "centre":
        centre = sum(bbox_vert, Vector())
        centre /= 8
        return centre
    elif arg == "2d":
        corner2d = [corner.to_2d() for corner in bbox_vert]
        return corner2d[::2]
    elif arg == "3d":
        return bbox_vert


def recalc_normals(obj):
    """Recalculate normals in object"""

    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")
    bpy.ops.object.select_all(action="DESELECT")


def face_sel(obj, pos, edge_verts=[]):
    """Select faces facing specified direction (top, bottom, edge)"""

    bpy.context.view_layer.objects.active = obj
    mesh = obj.data
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_mode(type="FACE")
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    kd = make_kd_tree(edge_verts)
    for face in obj.data.polygons:
        if pos == "edge":
            # check vertical faces
            if abs(face.normal.z) <= 0.5:
                # check if face contains vertices from list
                face_edges = []
                for ind in face.vertices:
                    face_edges.append(obj.data.vertices[ind].co)
                if verts_in(kd, face_edges):
                    bm.faces[face.index].select = True
        elif pos == "top":
            bm.faces[face.index].select = face.normal.z > 0.5
        elif pos == "bot":
            bm.faces[face.index].select = face.normal.z < -0.5
        else:
            logger.error("Specify pos")
    bmesh.update_edit_mesh(mesh)


def face_desel(obj):
    """Deselect all faces"""

    mesh = obj.data
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(mesh)
    bm.faces.ensure_lookup_table()
    for face in obj.data.polygons:
        bm.faces[face.index].select = False


def create_collection(name):
    """Creat and link objects to collection"""

    if not bpy.data.collections.get(name):
        newCol = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(newCol)
    return bpy.data.collections.get(name)


def remove_collection(name):
    """Remove collection"""

    remCol = bpy.context.scene.collection.children.get(name)
    bpy.data.collections.remove(remCol)


def link_obj_to_collection(obj, target_coll):
    """Loop through all collections the obj is linked to and unlink it from there, then link to targed collection"""

    for coll in obj.users_collection:
        coll.objects.unlink(obj)
    target_coll.objects.link(obj)


def apply_all_transform_obj(obj):
    """Apply all object transfromations"""

    obj.select_set(True)
    bpy.ops.object.transform_apply()
    obj.select_set(False)


def save_pcb_blend(path, apply_transforms=False):
    """Save blendfile"""

    bpy.ops.file.pack_all()
    if apply_transforms:
        for obj in bpy.context.scene.objects:
            apply_all_transform_obj(obj)
    bpy.ops.wm.save_as_mainfile(filepath=path)
