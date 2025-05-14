"""Schema for gerber2blend configuration file"""

from marshmallow import fields, ValidationError, Schema, EXCLUDE  # type: ignore
from typing import Any, Set, List
import re


class Color(fields.Field):
    """Custom Marshmallow field for validating color as a preset or a hex pair."""

    HEX_PATTERN = r"^#?([0-9A-Fa-f]{6})\W+#?([0-9A-Fa-f]{6})$"

    def __init__(self, presets: Set[str] = set(), *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.presets = presets

    def _deserialize(self, value: str, attr: Any, data: Any, **kwargs: Any) -> List[str]:
        if isinstance(value, str):
            if value in self.presets:
                return [value]

            if match := re.findall(self.HEX_PATTERN, value):
                return match

        raise ValidationError(
            f"Not a valid color format. Use a preset name ({', '.join(self.presets)}) or a pair of hex values."
        )


class BaseSchema(Schema):
    """
    A base schema for configuration definitions.
    This schema ensures that:
    - unknown fields are ignored during deserialization and not included in the parsed config
    - the schema is used only for loading (all fields are marked as `load_only`)
    - all fields are required, enforcing strict input validation
    """

    class Meta:
        unknown = EXCLUDE

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        for field in self.declared_fields.values():
            field.load_only = True
            field.required = True


def get_schema_field(schema_class: type[BaseSchema], field_name: str) -> fields.Field:
    """Get declared schema field by name."""
    try:
        schema_field = schema_class._declared_fields[field_name]
        return schema_field
    except KeyError:
        raise RuntimeError(f"Schema field '{field_name}' could not be found in {schema_class.__name__}")


class SettingsSchema(BaseSchema):
    PRJ_EXTENSION = fields.String()
    FAB_DIR = fields.String()
    DPI = fields.Number()  # type: ignore
    DEFAULT_BRD_THICKNESS = fields.Number()  # type: ignore
    SILKSCREEN = Color(presets={"White", "Black"}, allow_none=True)
    SOLDERMASK = Color(presets={"Black", "White", "Green", "Blue", "Red"}, allow_none=True)
    USE_INKSCAPE = fields.Bool()
    GENERATE_GLTF = fields.Bool()


class GerberFilenamesSchema(BaseSchema):
    EDGE_CUTS = fields.String()
    PTH = fields.String(allow_none=True)
    NPTH = fields.String(allow_none=True)
    IN = fields.String(allow_none=True)
    FRONT_SILK = fields.String()
    BACK_SILK = fields.String()
    FRONT_MASK = fields.String()
    BACK_MASK = fields.String()
    FRONT_CU = fields.String()
    BACK_CU = fields.String()
    FRONT_FAB = fields.String(allow_none=True)
    BACK_FAB = fields.String(allow_none=True)
    FRONT_PASTE = fields.String(allow_none=True)
    BACK_PASTE = fields.String(allow_none=True)


class EffectsSchema(BaseSchema):
    STACKUP = fields.Bool()
    SOLDER = fields.Bool()
    IGNORE_VIAS = fields.Bool()


class ConfigurationSchema(BaseSchema):
    """Parent schema for configuration file"""

    SETTINGS = fields.Nested(SettingsSchema)
    GERBER_FILENAMES = fields.Nested(GerberFilenamesSchema)
    EFFECTS = fields.Nested(EffectsSchema)
    STAGES = fields.List(fields.Dict())
