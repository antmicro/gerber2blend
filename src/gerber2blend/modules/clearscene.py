"""Module for clearing default Scene."""

import bpy
import gerber2blend.core.module


class ClearScene(gerber2blend.core.module.Module):
    """Module for clearing the scene."""

    def execute(self) -> None:
        """Execute ClearScene module."""
        clear_scene()


def clear_scene() -> None:
    """Clear the current scene."""
    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)
    while len(bpy.context.scene.collection.children) > 0:
        bpy.data.collections.remove(bpy.context.scene.collection.children[0])
