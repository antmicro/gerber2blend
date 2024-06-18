"""Module for configuring input data."""

import os
from os import getcwd, path
import gerber2blend.modules.file_io as fio
import gerber2blend.core.blendcfg
from typing import Dict, Any, List, Tuple
import logging
import argparse

# displacement map outputs from gerber -> png conversion
OUT_F_DISPMAP = "F_dispmap"
OUT_B_DISPMAP = "B_dispmap"
# names of intermediate files in the fab/SVG/ directory, without extension
# Gerber files used as input are copied under these names
GBR_EDGE_CUTS = "Edge_Cuts"
GBR_PTH = "PTH-drl"
GBR_NPTH = "NPTH-drl"
GBR_F_SILK = "F_SilkS"
GBR_B_SILK = "B_SilkS"
GBR_F_MASK = "F_Mask"
GBR_B_MASK = "B_Mask"
GBR_F_CU = "F_Cu"
GBR_B_CU = "B_Cu"
GBR_F_FAB = "F_Fab"
GBR_B_FAB = "B_Fab"
# compared to the above, this is used as a constant prefix for the name.
# There will be many inner layers, so each is suffixed in increments of
# 1, starting from 0 (In_0, In_1, ..)
GBR_IN = "In"

# This module is used to share variables between modules.
# Variables are only accessible after running init_global() in main function.
# https://stackoverflow.com/questions/13034496/using-global-variables-between-files

logger = logging.getLogger(__name__)

CWD: str = ""
blendcfg: Dict[str, Any] = {}
args: argparse.Namespace
g2b_dir_path: str = ""
png_path: str = ""
gbr_path: str = ""
svg_path: str = ""
pcb_blend_path: str = ""
mat_blend_path: str = ""
mat_library_path: str = ""
model_library_path: str = ""
PCB_name: str = ""
fab_path: str = ""
prj_path: str = ""
stackup_data: List[Tuple[str, float]] = []
pcbthickness: float = 0.0
pcbscale: float = 0.0


def init_global(arguments: argparse.Namespace) -> None:
    """Initialize global variables used across modules.

    Args:
    ----
        arguments: CLI arguments

    """
    global prj_path
    global blendcfg
    global args
    global g2b_dir_path

    prj_path = getcwd() + "/"
    g2b_dir_path = path.dirname(__file__) + "/.."

    # Create blendcfg if it does not exist
    gerber2blend.core.blendcfg.check_and_copy_blendcfg(prj_path, g2b_dir_path)
    # Read blendcfg file
    blendcfg = gerber2blend.core.blendcfg.open_blendcfg(prj_path, arguments.config_preset)

    configure_paths(arguments)
    configure_constants(arguments)

    args = arguments


def configure_paths(arguments: argparse.Namespace) -> None:
    """Configure global paths that will be searched for HW files.

    Args:
    ----
        arguments: CLI arguments

    """
    global fab_path
    global png_path
    global gbr_path
    global svg_path
    global pcb_blend_path
    global mat_blend_path
    global mat_library_path
    global model_library_path
    global PCB_name
    global prj_path

    fab_path = prj_path + blendcfg["SETTINGS"]["GERBER_DIR"] + "/"
    if not os.path.isdir(fab_path):
        raise RuntimeError(
            f"There is no {blendcfg['SETTINGS']['GERBER_DIR']}/ directory in the current working directory! ({prj_path})"
        )

    # Determine the name of the PCB to use as a name for the .blend
    if arguments.blend_path is None:
        PCB_name = fio.read_pcb_name(prj_path)
        pcb_blend_path = fab_path + PCB_name + ".blend"
    else:
        PCB_name = arguments.blend_path.split("/")[-1].replace(".blend", "")
        pcb_blend_path = path.abspath(arguments.blend_path)

    png_path = fab_path + "PNG/"
    gbr_path = fab_path + "GBR/"
    svg_path = fab_path + "SVG/"

    # paths:
    mat_blend_path = g2b_dir_path + "/templates/PCB_materials.blend"


def configure_constants(arguments: argparse.Namespace) -> None:
    """Configure common constants.

    Args:
    ----
        arguments: CLI arguments

    """
    global pcbscale

    blender_ratio = 2.8349302554764217
    pcbscale = 1000 * blender_ratio
