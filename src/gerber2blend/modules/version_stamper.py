import os
import subprocess
from typing import Optional
import bpy
import gerber2blend
import logging
import gerber2blend.modules.custom_utilities as cu
import gerber2blend.modules.config as cfg
import importlib.metadata


logger = logging.getLogger(__name__)


class VersionStamper(gerber2blend.core.module.Module):
    """Module to add version stamps to the generated PCB."""

    def execute(self) -> None:
        """Run the module."""
        logger.info("Stamping the generated board with revisions..")

        g2b_version = importlib.metadata.metadata("gerber2blend")["Version"]
        set_custom_property("G2B_VERSION", g2b_version)

        project_rev = read_git_repository_hash(cfg.prj_path)
        if project_rev is None:
            project_rev = ""
        set_custom_property("G2B_PROJECT_GIT_REV", project_rev)

        logger.info(f"Generated with gerber2blend version: {g2b_version}")
        logger.info(f"PCB project Git commit: {project_rev}")

        cu.save_pcb_blend(cfg.pcb_blend_path)


def read_git_repository_hash(path: str) -> Optional[str]:
    """Read the short commit hash of the Git repository at the given path.

    If there is no Git repository at the given path or an error occurs,
    returns None.
    Additionally, if the repository contains modifications, '-dirty' suffix
    is appended to the commit hash.
    """
    try:
        return (
            subprocess.check_output(["git", "describe", "--always", "--dirty"], cwd=path).decode("utf-8").strip(" \n")
        )
    except Exception as e:
        logger.warning(f"Failed to read Git commit hash: {e}")
        return None


def set_custom_property(key: str, value: str) -> None:
    """Append extra metadata to the main PCB collection."""
    board = cu.create_collection(cfg.PCB_name)
    board[key] = value
