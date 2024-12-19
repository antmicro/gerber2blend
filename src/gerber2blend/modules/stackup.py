"""Module responsible for stackup read and parse."""

import json
from typing import List, Tuple
import gerber2blend.modules.config as config
import os.path
import logging
import functools


logger = logging.getLogger()


class StackupInfo:
    """Stackup information."""

    stackup_data: List[Tuple[str, float, str]] = []
    """ Contains layer name <-> layer thickness <-> user layer name mappings

    If no stackup.json is provided, this will be empty.
    """

    thickness: float = 0.0
    """ Calculated thickness of the PCB

    This is calculated based on the stackup file. If no stackup.json is provided,
    this is configured with the value of blendcfg["SETTINGS"]["DEFAULT_BRD_THICKNESS"].
    """


def get() -> StackupInfo:
    """Get the stackup information for the current board project.

    Stackup information is generated based on the blendcfg configuration:
    - If stackup generation is not enabled, the stackup data is generated
      based on default values (board thickness).
    - If stackup is enabled and data was not loaded yet, it is loaded from
      fab/stackup.json. The file is only loaded once, and a cached stackup
      is returned in consecutive calls to get().
    """
    return _load_stackup_from_file()


def _load_stackup_from_file() -> StackupInfo:
    """Load stackup data from file specified in the current configuration."""
    # read stackup from stackup.json
    filepath = os.path.join(config.fab_path, "stackup.json")
    if config.blendcfg["EFFECTS"]["STACKUP"]:
        calculated_thickness, stackup_data = _parse_stackup_from_file(filepath)
    else:
        calculated_thickness = config.blendcfg["SETTINGS"]["DEFAULT_BRD_THICKNESS"]
        stackup_data = []

    info = StackupInfo()
    info.stackup_data = stackup_data
    info.thickness = calculated_thickness
    return info


@functools.cache
def _parse_stackup_from_file(file_path: str) -> Tuple[float, List[Tuple[str, float, str]]]:
    """Parse the stackup data from the given JSON file.

    Returns
    -------
        [0]: Calculated thickness of the PCB
        [1]: List of PCB name <-> thickness pairs

    """
    stackup_data = []
    calculated_thickness = config.blendcfg["SETTINGS"]["DEFAULT_BRD_THICKNESS"]

    try:
        logger.debug("Loading stackup data from: %s", file_path)
        if not os.path.exists(file_path):
            logger.warning("Error while reading stackup.json!")
        else:
            with open(file_path) as stackup_json_file:
                stackup_json_data = json.load(stackup_json_file)

            stackup_data = [
                (layer["name"], layer["thickness"], layer["user-name"]) for layer in stackup_json_data["layers"]
            ]
            calculated_thickness = 0.0
            for layer in stackup_json_data["layers"]:
                if layer["thickness"] is not None:
                    calculated_thickness += float(layer["thickness"])

            logger.debug("Found stackup data: " + str(stackup_data))
            logger.debug("Calculated thickness: " + str(calculated_thickness))
    except Exception as e:
        logger.warning("Error while reading stackup.json!", exc_info=True)
        raise RuntimeError("Could not read stackup.json") from e

    return calculated_thickness, stackup_data
