"""Module performing input/output operations on files."""

import bpy
import os
import sys
import logging
import gerber2blend.modules.config as config
from pathlib import Path
from typing import Optional, List, Callable, Generator, Any
from io import TextIOWrapper
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DEFAULT_PCB_NAME = "unknownpcb"


def mkdir(file_path: Path) -> None:
    """Create a directory at the specified path.

    Wraps any errors with a nicer error exception.
    """
    try:
        if not file_path.exists():
            file_path.mkdir()
    except OSError as e:
        raise RuntimeError(f"Could not create folder at path {str(file_path)}: {repr(e)}") from e


def read_pcb_name_from_prj(prj_path: Path, extension: str) -> str:
    """Try reading the PCB name from a project file at `prj_path` using extension specified in config.

    This function will fail and throw a `RuntimeError` if `prj_path` is not a valid project directory.
    """
    project_file = [file for file in prj_path.iterdir() if file.suffix == extension]

    if len(project_file) != 1:
        logger.error(f"There should be only one {extension} file in project main directory!")
        logger.error("Found: " + repr(project_file))
        raise RuntimeError(f"Expected single {extension} file in current directory, got {len(project_file)}")

    pcb_name = project_file[0].stem
    logger.debug(f"PCB name: {pcb_name}")
    return pcb_name


def read_pcb_name(prj_path: Path) -> str:
    """Read the PCB name from the current EDA project."""
    extension = config.blendcfg["SETTINGS"]["PRJ_EXTENSION"]
    if extension != "":
        try:
            return read_pcb_name_from_prj(prj_path, extension)
        except Exception:
            logger.warning(f"Failed to find {extension} file!")
        # further logic can be added in a similar way as above

    # default case
    logger.warning("Using default value for PCB name")
    return DEFAULT_PCB_NAME


@contextmanager
def stdout_redirected(to: str = os.devnull) -> Generator[None, Any, None]:
    """Redirect the standard output to dev/null.

    This context manager temporarily redirects `sys.stdout` to a specified target file or stream.
    During the redirection, any output written to `print()` or `sys.stdout` will be written to the target
    instead of the original `stdout`. After exiting the context, `sys.stdout` is restored to its original state.

    https://blender.stackexchange.com/questions/6119/suppress-output-of-python-operators-bpy-ops
    """
    fd = sys.stdout.fileno()

    def _redirect_stdout(to: TextIOWrapper) -> None:
        sys.stdout.close()  # + implicit flush()
        os.dup2(to.fileno(), fd)  # fd writes to 'to' file
        sys.stdout = os.fdopen(fd, "w")  # Python writes to fd

    with os.fdopen(os.dup(fd), "w") as old_stdout:
        with open(to, "w") as file:
            _redirect_stdout(to=file)
        try:
            yield  # allow code to be run with the redirected stdout
        finally:
            _redirect_stdout(to=old_stdout)  # restore stdout


########################################


def import_from_blendfile(
    blendfile: Path, data_type: str, filter_func: Callable[[str], bool] = lambda x: True
) -> List[str]:
    """Import data from another Blender file."""
    try:
        with bpy.data.libraries.load(str(blendfile)) as (data_from, data_to):
            filtered_data = list(filter(filter_func, getattr(data_from, data_type)))
            setattr(data_to, data_type, filtered_data)
            logger.debug(f"found data {data_type} in file {str(blendfile)}")
            return filtered_data
    except Exception:
        logger.error(f"failed to open blend file {str(blendfile)}")
    return []


def get_data_from_blendfile(
    blendfile: Path, data_type: str, filter_func: Callable[[str], bool] = lambda x: True
) -> Optional[List[str]]:
    """List data from another Blender file without including it in current file."""
    result = None
    try:
        with bpy.data.libraries.load(str(blendfile)) as (data_from, data_to):
            result = list(filter(filter_func, getattr(data_from, data_type)))
            logger.debug(f"found data {data_type} in file {str(blendfile)}")
    except Exception:
        logger.error(f"failed to open blend file {str(blendfile)}")
    return result
