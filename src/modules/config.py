import os
import sys
from os import getcwd, path as pth
import modules.fileIO as fio
import core.blendcfg
from xdg.BaseDirectory import load_data_paths  # type: ignore
from typing import Dict, Any
import logging

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
GBR_IN = "In_"

# This module is used to share variables between modules.
# Variables are only accessible after running init_global() in main function.
# https://stackoverflow.com/questions/13034496/using-global-variables-between-files

logger = logging.getLogger(__name__)

CWD: str = ""
blendcfg: Dict[str, Any] = {}
args: str = ""
g2b_dir_path: str = ""
png_path: str = ""
gbr_path: str = ""
svg_path: str = ""
pcb_blend_path: str = ""
mat_blend_path: str = ""
mat_library_path: str = ""
model_library_path: str = ""
PCB_name: str = ""
path: str = ""
stackup_data: str = ""
pcbthickness: str = ""
pcbscale: str = ""


def init_global(arguments):
    """Initialize global variables used across modules

    Args:
        arguments: CLI arguments
    """
    global CWD
    global blendcfg
    global args
    global g2b_dir_path

    CWD = getcwd() + "/"
    g2b_dir_path = pth.dirname(__file__) + "/.."

    # Create blendcfg if it does not exist
    core.blendcfg.check_and_copy_blendcfg(CWD, g2b_dir_path)
    # Read blendcfg file
    blendcfg = core.blendcfg.open_blendcfg(CWD, arguments.config_preset)

    configure_paths(arguments)
    configure_constants(arguments)
    configure_stackup(arguments)

    args = arguments


def configure_paths(arguments):
    """Configure global paths that will be searched for HW files

    Args:
        arguments: CLI arguments
    """
    global png_path
    global gbr_path
    global svg_path
    global pcb_blend_path
    global mat_blend_path
    global mat_library_path
    global model_library_path
    global PCB_name
    global path

    path = CWD + "fab/"
    if not os.path.isdir(path):
        raise RuntimeError(
            "There is no fab/ directory in the current working directory! (%s)" % CWD
        )

    # Determine the name of the PCB to use as a name for the .blend
    if arguments.blend_path is None:
        PCB_name = fio.read_pcb_name(CWD)
        pcb_blend_path = path + PCB_name + ".blend"
    else:
        PCB_name = arguments.blend_path.split("/")[-1].replace(".blend", "")
        pcb_blend_path = pth.abspath(arguments.blend_path)

    png_path = path + "PNG/"
    gbr_path = path + "GBR/"
    svg_path = path + "SVG/"

    # paths:
    mat_blend_path = g2b_dir_path + "/templates/materials.blend"

    mat_library_path = model_library_path + "/lib/materials/pcb_materials.blend"


def configure_constants(arguments):
    """Configure common constants

    Args:
        arguments: CLI arguments
    """
    global pcbscale

    blender_ratio = 2.8349302554764217
    pcbscale = 1000 * blender_ratio


def configure_stackup(arguments):
    """Configure board thickness

    Args:
        arguments: CLI arguments
    """
    global stackup_data
    global pcbthickness

    # read stackup from stackup.json
    if blendcfg["EFFECTS"]["STACKUP"]:
        if pth.isfile(path + "/stackup.json"):
            pcbthickness, stackup_data = fio.parse_stackup(path + "/stackup.json")
        else:
            logger.error(
                "No stackup.json file found. See documentation for stackup.json format. Aborting."
            )
            logger.error("Tried looking in: %s", path)
            exit(1)
    else:
        pcbthickness = blendcfg["SETTINGS"]["DEFAULT_BRD_THICKNESS"]
        stackup_data = []
