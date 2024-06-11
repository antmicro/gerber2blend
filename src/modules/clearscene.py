import bpy
import core.module


class ClearScene(core.module.Module):
    """Module for clearing the scene"""

    def execute(self) -> None:
        clear_scene()


def clear_scene() -> None:
    """Helper method to clear the current scene"""
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)
    while len(bpy.context.scene.collection.children) > 0:
        bpy.data.collections.remove(bpy.context.scene.collection.children[0])
