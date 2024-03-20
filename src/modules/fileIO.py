import json
import bpy  # type: ignore
from os import listdir
import logging
import modules.config as config
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_PCB_NAME = "unknownpcb"


def parse_stackup(path):
    """Retrieve stackup data from JSON"""

    stackup_data = []
    pcbthickness = 0

    try:
        stackup_json_file = open(path)
        stackup_json_data = json.load(stackup_json_file)
        stackup_json_file.close()

        stackup_data = [
            (layer["name"], layer["thickness"]) for layer in stackup_json_data["layers"]
        ]

        for layer in stackup_json_data["layers"]:
            if layer["thickness"] is not None:
                pcbthickness += float(layer["thickness"])

        logger.debug("Found stackup data: " + str(stackup_data))
        logger.debug("Calculated thickness: " + str(pcbthickness))

    except Exception:
        raise RuntimeError("Failed to read data from stackup.json file, aborting")

    return pcbthickness, stackup_data


def read_pcb_name_from_prj(path, extension):
    """Try reading the PCB name from a project file at `path` using extension specified in config

    This function will fail and throw a `RuntimeError` if `path` is
    not a valid project directory.
    """
    files = listdir(path)
    project_file = [f for f in files if f.endswith(extension)]

    if len(project_file) != 1:
        logger.error(
            f"There should be only one {extension} file in project main directory!"
        )
        logger.error("Found: " + repr(project_file))
        raise RuntimeError(
            f"Expected single {extension} file in current directory, got %d"
            % len(project_file)
        )

    name = Path(project_file[0]).stem
    logger.debug("PCB name: %s", name)
    return name


def read_pcb_name(path):
    """Read the PCB name from the current EDA project"""

    extension = config.blendcfg["SETTINGS"]["PRJ_EXTENSION"]
    if extension != "":
        try:
            return read_pcb_name_from_prj(path, extension)
        except Exception:
            logger.warning(f"Failed to find {extension} file!")
        # further logic can be added in a similar way as above

    # default case
    logger.warning("Using default value for PCB name")
    return DEFAULT_PCB_NAME


########################################


def import_from_blendfile(blendfile, data_type, filter_func=lambda x: True):
    """Import data from another Blender file"""

    try:
        with bpy.data.libraries.load(blendfile) as (data_from, data_to):
            filtered_data = list(filter(filter_func, getattr(data_from, data_type)))
            setattr(data_to, data_type, filtered_data)
            logger.debug("found data " + data_type + " in file " + blendfile)
            return filtered_data
    except Exception:
        logger.error("failed to open blend file " + blendfile)
    return None


def get_data_from_blendfile(blendfile, data_type, filter_func=lambda x: True):
    """List data from another Blender file without including it in current file"""

    result = None
    try:
        with bpy.data.libraries.load(blendfile) as (data_from, data_to):
            result = list(filter(filter_func, getattr(data_from, data_type)))
            logger.debug("found data " + data_type + " in file " + blendfile)
    except Exception:
        logger.error("failed to open blend file " + blendfile)
    return result
