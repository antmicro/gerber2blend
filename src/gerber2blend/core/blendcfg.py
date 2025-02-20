"""Module responsible for parsing config file."""

import logging
from shutil import copyfile
from typing import Any, Dict, List
import ruamel.yaml
from marshmallow import ValidationError  # type: ignore
from gerber2blend.core.schema import BaseSchema

logger = logging.getLogger(__name__)

# Name of the configuration file
# This is the name that is used for the template
# and when copying the template to a local config.
BLENDCFG_FILENAME = "blendcfg.yaml"


class BlendcfgValidationError(Exception):
    """
    Blendcfg validation error custom exception.
    Accepts strings and marshmallow ValidationError lists or dicts.
    """

    def __init__(self, errors: List[Any] | Dict[Any, Any] | str) -> None:
        self.errors = errors
        if isinstance(errors, str):
            msg = errors
        else:
            msg = "Blendcfg validation error\n" + self._format_errors(errors)
        super().__init__(msg)

    def _format_errors(self, err: List[Any] | Dict[Any, Any], indent: int = 2) -> str:
        """Format nested dictionary into indented human-readable string."""
        if isinstance(err, list):
            return "\n".join(err)

        lines = []
        for key, val in err.items():
            if isinstance(val, dict):
                lines.append(" " * indent + f"{key}:")
                lines.append(self._format_errors(val, indent + 4))
            elif isinstance(val, list):
                for msg in val:
                    lines.append(" " * indent + f"{key}: {msg}")
            else:
                lines.append(" " * indent + f"{key}: {val}")
        return "\n".join(lines)


def open_blendcfg(path: str, config_preset: str) -> Dict[str, Any]:
    """Open configuration file from the specified path."""
    project_cfg_path = path + BLENDCFG_FILENAME

    yaml = ruamel.yaml.YAML(typ="safe")
    yaml.indent(mapping=2, sequence=4, offset=2)
    with open(project_cfg_path) as prj_file:
        project_cfg = yaml.load(prj_file)
        logger.info(f"Loaded configuration file: {project_cfg_path}")

    if not isinstance(project_cfg, dict):
        raise BlendcfgValidationError(f"Invalid config loaded.")

    if not config_preset:
        if "default" not in project_cfg:
            raise BlendcfgValidationError(f"Default config is not defined in {BLENDCFG_FILENAME}.")
        raw_config = project_cfg["default"]
    else:
        if config_preset not in project_cfg:
            raise BlendcfgValidationError(f"Unknown blendcfg preset: {config_preset}")
        raw_config = update_yamls(project_cfg["default"], project_cfg[config_preset])
    logger.info(f"Used preset: {config_preset if config_preset else 'default'}")
    return raw_config


def validate_blendcfg(raw_config: Dict[str, Any], schema: BaseSchema) -> Dict[str, Any]:
    """Validate raw config (string) using defined schema."""
    try:
        config = schema.load(raw_config)
        return config
    except ValidationError as e:
        raise BlendcfgValidationError(e.messages)


def copy_blendcfg(file_path: str, src_path: str) -> None:
    """Copy blendcfg to project's directory."""
    logger.warning(f"Copying default config from template.")
    copyfile(src_path + "/templates/" + BLENDCFG_FILENAME, file_path + BLENDCFG_FILENAME)


def merge_blendcfg(file_path: str, src_path: str, overwrite: bool = False) -> None:
    """
    Merge template blendcfg with local one in project's directory and save changes to file.
    When overwrite is enabled, values set in local config will be replaced with the ones in template.
    When overwrite is disabled, settings that are missing in the local config will be added from template
    (serves as a fallback in situations when required config keys are missing to prevent crashes).
    """
    prompt = " (overwriting local values)" if overwrite else ""
    logger.warning(f"Merging default config from template with local one found{prompt}.")
    project_cfg_path = file_path + "/" + BLENDCFG_FILENAME
    template_cfg_path = src_path + "/templates/" + BLENDCFG_FILENAME

    yaml = ruamel.yaml.YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)

    with open(project_cfg_path) as prj_file, open(template_cfg_path) as temp_file:
        project_cfg = yaml.load(prj_file)
        template_cfg = yaml.load(temp_file)

    if overwrite:
        cfg = update_yamls(project_cfg, template_cfg)

    else:
        cfg = update_yamls(template_cfg, project_cfg)

    merged_cfg = project_cfg = file_path + "/" + BLENDCFG_FILENAME
    with open(merged_cfg, "w") as file:
        yaml.dump(cfg, file)


def update_yamls(
    source: Dict[str, Any],
    target: Dict[str, Any],
) -> Dict[str, Any]:
    """Recursively overwrite target values with source values. Adds missing keys found in source."""
    for key, value in source.items():
        if key in target:
            if isinstance(value, dict) and isinstance(target[key], dict):
                update_yamls(value, target[key])
        else:
            target[key] = value
    return target
