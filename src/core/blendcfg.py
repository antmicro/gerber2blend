import logging
from typing import Any, Callable, Dict, Optional
import yaml
from shutil import copyfile
import os.path

logger = logging.getLogger(__name__)

# Name of the configuration file
# This is the name that is used for the template
# and when copying the template to a local config.
BLENDCFG_FILENAME = "blendcfg.yaml"


class Field:
    """Represents schema of a configuration field"""

    def __init__(self, type: str, conv: Optional[Callable[[Any], Any]] = None) -> None:
        """Create a configuration field

        Args:
            type: String name of the type of the field. One of: "color",
                  "background", "bool", "number", "color_preset", "transition".
            conv: Converter function to use. When set, the value of the field from
                  `blendcfg.yaml` is passed to this function. Value returned from
                  the function is still checked against the field's specified type.
        """
        self.type = type
        self.conv = conv


def check_and_copy_blendcfg(file_path, g2b_path):
    if not os.path.exists(file_path + BLENDCFG_FILENAME):
        logger.warning("Config file not found, copying default template")
        copyfile(
            g2b_path + "/templates/" + BLENDCFG_FILENAME, file_path + BLENDCFG_FILENAME
        )


def is_color(arg: str) -> bool:
    hex_chars = "0123456789ABCDEF"
    return len(arg) == 6 and all([c in hex_chars for c in arg])


def is_color_preset(arg: str | list[str]) -> bool:

    presets = ["White", "Black", "Blue", "Red", "Green"]  # allowed color keywords
    if isinstance(arg, list):
        arg = arg[0]
    if arg in presets:
        return True
    if is_color(arg):
        return True
    return False


def is_top_bottom(arg) -> bool:
    first = arg[0] == "True"
    if first and len(arg) == 1:
        return False  # missing backgrounds to use
    correct_bg = ["Black", "White", "SeeThrough"]
    return all([bg in correct_bg for bg in arg[1:]])


def is_transition(arg) -> bool:
    first = arg[0] == "True"
    if first and len(arg) == 1:
        return False  # missing backgrounds to use
    options = ["All", "Renders"]
    return all([opt in options for opt in arg[1:]])


# parse color
def hex_to_rgba(hex, alpha: bool = True):
    rgb = []
    for i in (0, 2, 4):
        decimal = int(hex[i : i + 2], 16)
        rgb.append(decimal / 255)
    if alpha:
        rgb.append(1)
    return tuple(rgb)


def parse_true_false(arg):
    # change first to bool, rest remains as list of strings
    tmp = arg.replace(",", "").split()
    tmp[0] = True if tmp[0] == "True" else False
    return tmp


def parse_strings(arg):
    tmp = arg.replace(",", "").split()
    return tmp


# Schema for blendcfg.yaml file
CONFIGURATION_SCHEMA = {
    "SETTINGS": {
        "PRJ_EXTENSION": Field("string"),
        "GERBER_DIR": Field("string"),
        "DPI": Field("number"),
        "DEFAULT_BRD_THICKNESS": Field("number"),
        "SILKSCREEN": Field("color_preset", conv=parse_strings),
        "SOLDERMASK": Field("color_preset", conv=parse_strings),
        "USE_INKSCAPE": Field("bool"),
    },
    "GERBER_FILENAMES": {
        "EDGE_CUTS": Field("string"),
        "PTH": Field("string"),
        "NPTH": Field("string"),
        "IN": Field("string"),
        "FRONT_SILK": Field("string"),
        "BACK_SILK": Field("string"),
        "FRONT_MASK": Field("string"),
        "BACK_MASK": Field("string"),
        "FRONT_CU": Field("string"),
        "BACK_CU": Field("string"),
        "FRONT_FAB": Field("string"),
        "BACK_FAB": Field("string"),
    },
    "EFFECTS": {
        "STACKUP": Field("bool"),
    },
}


def check_throw_error(cfg, args, schema: Field):
    """Validate the given configuration entry

    Args:
        cfg: entire deserialized blendcfg.yaml file
        args: a list of names leading to the configuration entry that
              needs to be checked, for example: ["SETTINGS", "DPI"].
              Currently, there must be exactly two names present in the list!
        schema: schema for the field
    """
    missing_config = False
    val = None
    try:
        val = cfg.get(args[0]).get(args[1])
    except Exception:
        missing_config = True

    if val is None or missing_config:
        logger.error(f"[{args[0]}][{args[1]}] not found in {BLENDCFG_FILENAME}")
        raise RuntimeError("Configuration invalid")

    if schema.conv is not None:
        try:
            val = schema.conv(val)
            cfg[args[0]][args[1]] = val
        except Exception as e:
            logger.error(
                "Converting value [%s][%s] (= %s) failed: %e",
                args[0],
                args[1],
                val,
                str(e),
            )
            raise RuntimeError("Configuration invalid")

    not_schema_type_err = f"[{args[0]}][{args[1]}] is not a {schema.type}"
    color_type_err = f"[{args[0]}][{args[1]}] is not a color, should be hex color value"

    match schema.type:
        case "color":
            assert is_color(val), color_type_err
        case "background":
            assert is_top_bottom(val), not_schema_type_err
        case "bool":
            assert isinstance(val, bool), not_schema_type_err
        case "number":
            assert isinstance(val, float) or isinstance(val, int), not_schema_type_err
        case "color_preset":
            assert is_color_preset(val), color_type_err + " or presets"
        case "transition":
            assert is_transition(val), not_schema_type_err
        case "tuple":
            assert isinstance(val, tuple), not_schema_type_err
        case "string":
            assert isinstance(val, str), not_schema_type_err
        case _:
            raise RuntimeError(f"[{args[0]}][{args[1]}] is not a {schema.type}")


def validate_module_config(
    schema: dict[str, Field], conf: dict[str, Any], module_name: str
) -> bool:
    """Validates the module config against a given schema

    Returns:
        True: module configuration is valid
        False: module configuration is invalid
    """
    valid = True

    for name, field in schema.items():
        try:
            check_throw_error(conf, [module_name, name], field)
        except Exception as e:
            logger.error("Field %s invalid: %s", name, str(e))
            valid = False

    return valid


def validate_setting_dependencies(cfg):
    """Validate if certain blendcfg.yaml settings have their required dependencies"""
    # Left empty on purpose
    # If required, this can be expanded to include additional validation
    # for blencfg.yaml configuration entries, for example: a setting depends
    # on a different setting to be enabled.


def check_and_parse_blendcfg(cfg) -> Dict[str, Any]:
    """Validate and parse the blendcfg.yaml loaded from a file"""

    valid = True

    for module in cfg:
        if module not in CONFIGURATION_SCHEMA:
            continue

        # Check config for module
        if not validate_module_config(CONFIGURATION_SCHEMA[module], cfg, module):
            valid = False

    if not valid:
        raise RuntimeError("Configuration in blendcfg.yaml invalid")

    validate_setting_dependencies(cfg)

    return cfg


def open_blendcfg(path, config_preset) -> Dict[str, Any]:
    """Open configuration file from the specified path"""
    with open(path + BLENDCFG_FILENAME, "r") as bcfg:
        cfg = yaml.safe_load(bcfg)
        if config_preset not in cfg:
            raise RuntimeError(f"Unknown blendcfg preset: {config_preset}")
        return check_and_parse_blendcfg(cfg[config_preset])
