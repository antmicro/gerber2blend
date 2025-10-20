"""Scripts main execution file."""

import argparse
import importlib
import inspect
import logging
import pkgutil
import sys
from typing import Any, Optional
import gerber2blend.core.blendcfg as blendcfg
import gerber2blend.core.log
import gerber2blend.core.module
import gerber2blend.modules.config as config
from pathlib import Path

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments passed to gerber2blend."""

    def formatter(prog: str) -> argparse.HelpFormatter:
        return argparse.HelpFormatter(prog, max_help_position=35)

    parser = argparse.ArgumentParser(
        prog="gerber2blend",
        prefix_chars="-",
        formatter_class=formatter,
        description="Gerber to Blender pipeline runner for generating PCB 3D models from PCB production files",
    )
    parser.add_argument(
        "-d",
        "--debug",
        "-v",
        "--verbose",
        dest="debug",
        action="store_true",
        help="increase verbosity, print more information",
    )
    parser.add_argument(
        "-r",
        "--regenerate-pcb-blend",
        action="store_true",
        dest="regenerate",
        help="regenerate pcb.blend",
    )
    parser.add_argument(
        "-b",
        "--blend-path",
        dest="blend_path",
        help="specify path to input/output .blend file",
    )
    parser.add_argument(
        "-c",
        "--config",
        dest="config_preset",
        help="",
        type=str,
        default="default",
    )
    parser.add_argument(
        "-R",
        "--reset-config",
        help=(
            "reset local config settings to the values from the template and exit."
            "Copy blendcfg.yaml to CWD instead if there is no CWD config file found."
        ),
        action="store_true",
    )
    parser.add_argument(
        "-u",
        "--update-config",
        help=(
            "update local config settings with the additional ones found in the template and exit."
            "Copy blendcfg.yaml to CWD instead if there is no CWD config file found."
        ),
        action="store_true",
    )

    return parser.parse_args()


def import_python_submodules() -> None:
    """Import all available extension Python submodules from the environment."""
    # Look in the `modules` directory under site-packages
    modules_path = Path(__file__).parent / "modules"
    for _, module_name, _ in pkgutil.walk_packages([str(modules_path)], prefix="gerber2blend.modules."):
        logger.debug("Importing Python submodule: %s", module_name)
        try:
            importlib.import_module(module_name)
        except Exception as e:
            logger.warn("Python submodule %s failed to load!", module_name)
            logger.debug("Submodule load exception: %s", str(e))


def find_module(name: str) -> Optional[type]:
    """Find a class that matches the given module name.

    This matches a config module name, for example BOARD, to a Python
    class defined somewhere within the available Python environment.
    The class must derive from `Module` available in core/module.py.
    """
    for _, obj in inspect.getmembers(sys.modules["gerber2blend.modules"]):
        if not inspect.ismodule(obj):
            continue

        for subname, subobj in inspect.getmembers(obj):
            uppercase_name = subname.upper()
            if (
                inspect.isclass(subobj)
                and issubclass(subobj, gerber2blend.core.module.Module)
                and name == uppercase_name
            ):
                logger.debug("Found module: %s in %s", subname, obj)
                return subobj

    return None


def create_modules(config: list[dict[Any, Any]]) -> list[gerber2blend.core.module.Module]:
    """Create modules based on the blendcfg.yaml configuration file."""
    import_python_submodules()

    runnable_modules = []

    logger.debug("Execution plan:")
    for v in config:
        name = next(iter(v))
        logger.debug("Module %s:", name)

        # Find a class that matches the module name
        class_type = find_module(name)
        if not class_type:
            raise RuntimeError(
                f"Could not find module {name} anywhere! "
                "Have you defined a class for the module, and is it a subclass of gerber2blend.core.module.Module?"
            )

        # We got a type, we can now create the object
        # This is just a constructor call
        try:
            module = class_type()
            runnable_modules.append(module)
        except Exception as e:
            raise RuntimeError(f"Failed to create module {name}: {str(e)}") from e

    return runnable_modules


def run_modules_for_config(conf: dict[Any, Any]) -> None:
    """Run all module processing jobs for the specified blendcfg.yaml."""
    modules = create_modules(conf["STAGES"])

    logger.info("Number of modules to run: %d", len(modules))
    for job in modules:
        logger.info("Running module: %s", job)
        job.execute()
        logger.info("Finished running: %s", job)


def main() -> None:
    """Execute script's main function."""
    # Configure logger based on if we're debugging or not
    args = parse_args()
    gerber2blend.core.log.set_logging(args.debug)

    if args.blend_path and not Path(args.blend_path).is_file():
        logger.error(f"Model not found at path: {args.blend_path}")
        exit(1)

    try:
        if config.init_global(args):
            run_modules_for_config(config.blendcfg)

    except blendcfg.BlendcfgValidationError as e:
        logger.error("%s", str(e), exc_info=False)
        exit(1)

    except Exception as e:
        logger.error("An error has occured during processing!")
        logger.error("%s", str(e), exc_info=True)
        exit(1)


if __name__ == "__main__":
    main()
