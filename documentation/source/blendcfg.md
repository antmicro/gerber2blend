# Configuring blendcfg.yaml

You can customize outputs by editing the `blendcfg.yaml` file which defines rendering options and variants to be generated. 
The file needs to be placed in the main directory of the hardware project.
A default `blendcfg.yaml` is generated in the project directory when one does not exist.
Alternatively it can be copied manually from this repo, from the [`templates/blendcfg.yaml`](../../templates/blendcfg.yaml) file.

The file includes the following config sections:

### `SETTINGS`
General board and conversion settings:
* `PRJ_EXTENSION` - string containing EDA software main project file extension, used to read the PCB project name from it. Can be set to `""` if the extension is undefined. If no files with this extension are found, `unknownpcb` will be used as name. 
* `DPI` - resolution of bitmaps measure exported from Gerber files, influences quality of PCB soldermask shaders and board model creation time. Standard value is **600**. 
* `DEFAULT_BRD_THICKNESS` - default board thickness used to generate PCB model when rendering without stackup provided. Default value is **1.6**.
* `SILKSCREEN` - silkscreen marking color on PCB texture, options: `White` (default), `Black`
* `SOLDERMASK` - soldermask color on PCB texture, options: `Black` (default), `White`, `Green`, `Blue`, `Red`. To use custom RGB values, input a pair of hex values: `AABBCC, DDEEFF` (colors for areas with and without copper beneath). `gerber2blend` converts provided RGB codes to Blender color space.
* `USE_INKSCAPE` - helper Inkscape SVG convert operation that can be used for boards with footprints with overlapping holes that cause problems with generating a PCB mesh from Gerber-based SVG files. Requires Inkscape >1.2.

### `EFFECTS` section
Enables additional render effects:
* `STACKUP`- generates separate models for each layer of the PCB, requires `stackup.json` to be provided in the `fab/` directory. This file format is specified in the [Getting started secton](getting-started.md#sackup-format).

### `GERBER_FILENAMES` section

Configuration for input Gerber filenames.
Each of the following options specifies a wildcard pattern - the following operations are supported:
- `*` - match any amount of characters
- `?` - match exactly one character
- `[]` - match one of the specified characters (for example: `[abc]` will match characters `a`, `b` or `c`).

Gerber filenames:
* `EDGE_CUTS` - pattern for Edge Cuts Gerber
* `PTH` - pattern for the PTH drill files
* `NPTH` - pattern for the NPTH drill files
* `IN` - pattern for the Inner Copper layer Gerber, files matched by this pattern are treated as inner layers
* `FRONT_SILK` - pattern for the Front Silk Gerber
* `BACK_SILK` - pattern for the Back Silk Gerber
* `FRONT_MASK` - pattern for the Front Mask Gerber
* `BACK_MASK` - pattern for the Back Mask Gerber
* `FRONT_CU` - pattern for the Front Copper layer Gerber
* `BACK_CU` - pattern for the Back Copper layer Gerber
* `FRONT_FAB` - pattern for the Front Fab Gerber
* `BACK_FAB` - pattern for the Front Fab Gerber

### `STAGES` section
A list that defines modules to be run when executing `gerber2blend`.
The module names are followed by a `:`, for example:

```yaml
STAGES:
    - CLEARSCENE:
    - GERBCONVERT:
    - BOARD:
```

For description on how stage names from `blendcfg.yaml` are translated to Python modules for execution, see the [Processing pipeline](pipeline.md) chapter.
