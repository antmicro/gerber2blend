"""Module responsible for GBR to SVG and PNG conversion."""

import os
import re
import shutil
import logging
import glob
from pathlib import Path
from functools import partial
from multiprocessing import Pool
from typing import List, Tuple
from wand.image import Image  # type: ignore
from wand.color import Color  # type: ignore
import vtracer  # type: ignore
import gerber2blend.core.module
from gerber2blend.core.schema import GerberFilenamesSchema, get_schema_field
import gerber2blend.modules.config as config
import gerber2blend.modules.file_io as fio
import gerber2blend.modules.stackup as stackup
from gerber2blend.modules.config import (
    GBR_IN,
    GBR_PTH,
    GBR_NPTH,
    GBR_EDGE_CUTS,
    OUT_F_DISPMAP,
    OUT_B_DISPMAP,
    GBR_F_SILK,
    GBR_B_SILK,
    GBR_F_MASK,
    GBR_B_MASK,
    GBR_F_CU,
    GBR_B_CU,
    GBR_F_FAB,
    GBR_B_FAB,
    GBR_F_PASTE,
    GBR_B_PASTE,
    OUT_F_SOLDER,
    OUT_B_SOLDER,
)
import gerber  # type: ignore

HEX_BLACK = "#000000"
HEX_BLACK_ALPHA = "#00000000"  # with alpha
HEX_WHITE = "#ffffff"
HEX_WHITE_ALPHA = "#ffffffff"  # with alpha
# temporary files
TMP_F_SILKS = "tmp_fsilks"
TMP_B_SILKS = "tmp_bsilks"
TMP_F_MASK = "tmp_fmask"
TMP_B_MASK = "tmp_bmask"
TMP_F_MASK_SILKS = "tmp_fmask_for_silk"  # negated mask for silk cutout
TMP_B_MASK_SILKS = "tmp_bmask_for_silk"  # negated mask for silk cutout
MASK_BG_COLOR = "#aaaaaa"
MASK_FG_COLOR = "#ffffff"
MASK_FG_COLOR_ALPHA = "#ffffff99"
TMP_ALPHAW_PTH = "alphaw-PTH-drl"
TMP_ALPHAW_NPTH = "alphaw-NPTH-drl"

logger = logging.getLogger(__name__)


class GerbConvert(gerber2blend.core.module.Module):
    """Module to convert gerbers to the required intermediate files."""

    def execute(self) -> None:
        """Run the module."""
        do_prepare_build_directory()
        if config.blendcfg["EFFECTS"]["IGNORE_VIAS"]:
            do_remove_via_holes()
        do_convert_layer_to_png()
        do_generate_displacement_map_foundation()
        do_crop_pngs()
        prepare_solder()
        do_convert_gerb_to_svg()
        do_generate_displacement_maps()


def do_prepare_build_directory() -> None:
    """Prepare the build directory and populate it with required files.

    This function prepares the fabrication data directory for running board generation.
    Gerbers from the current hardware project (as defined in blendcfg.yaml)
    are copied to their correct location inside GBR/ directory, and optional GBRs
    are replaced with a dummy.
    """
    # Prepare paths; create subdirectories for intermediate steps files
    fio.mkdir(config.svg_path)
    fio.mkdir(config.png_path)
    fio.mkdir(config.gbr_path)

    # Remove old temp files
    remove_files_with_ext(config.png_path, ".png")
    remove_files_with_ext(config.gbr_path, ".gbr")
    remove_files_with_ext(config.svg_path, ".svg")

    # Name mapping of gerber files
    # This is to allow for using a unified name in all modules.
    gerb_file_renames = {
        "EDGE_CUTS": GBR_EDGE_CUTS,
        "PTH": GBR_PTH,
        "NPTH": GBR_NPTH,
        "IN": GBR_IN,
        "FRONT_SILK": GBR_F_SILK,
        "BACK_SILK": GBR_B_SILK,
        "FRONT_MASK": GBR_F_MASK,
        "BACK_MASK": GBR_B_MASK,
        "FRONT_CU": GBR_F_CU,
        "BACK_CU": GBR_B_CU,
        "FRONT_FAB": GBR_F_FAB,
        "BACK_FAB": GBR_B_FAB,
        "FRONT_PASTE": GBR_F_PASTE,
        "BACK_PASTE": GBR_B_PASTE,
    }
    # Inputs that are allowed to have many files.
    # For each matching input file, the file will be copied to
    # the blendcfg[SETTINGS][FAB_PATH]/GBR/ directory under the name:
    #   GERB_FILE_RENAMES[which_input] + <index_of_file> + ".gbr"
    # The files are indexed according to the lexicographical order of
    # their original file names.
    gerbs_with_many_files = [
        "IN",
    ]

    # Check all of the filenames specified in "GERBER_FILENAMES" and
    # move them to the build directory under the above specified names.
    gerbers_missing = False
    gbr_dir = config.blendcfg["SETTINGS"]["FAB_DIR"]
    for k, v in config.blendcfg["GERBER_FILENAMES"].items():
        if v is None:
            # Only makes sense to do this with singular gerber files
            if k not in gerbs_with_many_files:
                new_path = (config.gbr_path / gerb_file_renames[k]).with_suffix(".gbr")
                logger.info(f"Gerber file {k} missing. Replacing with empty file: {new_path}")
                new_path.touch()
            continue

        logger.info(f"Looking up {v} in {config.fab_path}...")
        fpath = config.fab_path / v
        matches = glob.glob(str(fpath))
        if len(matches) == 0:
            if not get_schema_field(GerberFilenamesSchema, k).required:
                logger.warning(f"Did not find optional {k} in path: {config.fab_path}")
            else:
                logger.error(f"Could not find required Gerber {k} with pattern: {v} in {gbr_dir}/ directory!")
                gerbers_missing = True
            continue

        # Handle inputs with many files
        if k in gerbs_with_many_files:
            # Sort the filelist, as glob.glob() does not guarantee a sorted output
            user_layer_names = stackup.get().stackup_data
            if not user_layer_names:
                logger.info("No stackup file found.")
                try:
                    matches = sorted(
                        matches,
                        key=lambda x: int(x.split("/")[-1].split("-In")[-1].replace("_Cu.gbr", "")),
                    )
                except Exception:
                    logger.warning("Inner layers don't use default readable naming scheme. Sorting alphabetically.")
                    logger.info("To ensure order of inner layers, please supply a stackup file.")
                    matches = sorted(matches)
            else:
                matches = sorted(
                    matches,
                    key=lambda x: int(
                        next(
                            layer["name"].replace("In", "").split(".Cu")[0]
                            for layer in user_layer_names
                            if layer["user-name"] in x
                        )
                    ),
                )
            if len(matches) == 0:
                logger.error(f"Could not find required Gerber {k} with pattern: {v} in {gbr_dir}/ directory!")
                gerbers_missing = True
            for i in range(0, len(matches)):
                gerber_path = matches[i]
                new_name = gerb_file_renames[k] + str(i) + ".gbr"
                new_path = config.gbr_path / new_name
                logger.info(f"Found {k}{i}: {gerber_path}, saving as: {new_path}")
                shutil.copy(gerber_path, new_path)
            continue

        gerber_path = matches[0]
        new_name = gerb_file_renames[k] + ".gbr"
        new_path = config.gbr_path / new_name

        logger.info(f"Found {k}: {gerber_path}, saving as: {new_path}")
        shutil.copy(gerber_path, new_path)

    if gerbers_missing:
        raise RuntimeError(f"One or more mandatory Gerber files are missing from the {gbr_dir}/ directory.")


def do_remove_via_holes() -> None:
    """Remove small PTH holes representing vias from input Gerber files."""
    pth_gbr_path = (config.gbr_path / GBR_PTH).with_suffix(".gbr")
    logger.info("Removing via holes from working copy of PTH Gerber file.")
    if not pth_gbr_path.exists():
        logger.info("PTH file is not present. No vias to remove.")
        return
    # override faulty gerber.read function
    with open(str(pth_gbr_path), "r") as f:
        data = f.read()
        pth_gbr_file = gerber.loads(data, str(pth_gbr_path))
    via_min_diameter = 0.5
    new_objects = []
    apertures_to_remove = []
    entered_apertures_to_remove = False
    for obj in pth_gbr_file.statements:
        # find apertures definitions and filter those below diameter threshold
        match type(obj):
            case gerber.gerber_statements.ADParamStmt:
                if obj.modifiers[0][0] <= via_min_diameter:
                    apertures_to_remove.append(obj.d)
            case gerber.gerber_statements.ApertureStmt:
                if obj.d in apertures_to_remove:
                    entered_apertures_to_remove = True
                else:
                    entered_apertures_to_remove = False
            case gerber.gerber_statements.CoordStmt:
                if entered_apertures_to_remove is True:
                    # do not add aperture to new_objects
                    continue
            case _:
                entered_apertures_to_remove = False
        new_objects.append(obj)

    pth_gbr_file.statements = new_objects
    pth_gbr_file.write(str(pth_gbr_path))


def do_convert_gerb_to_svg() -> None:
    """Convert required gerb files to SVG."""
    # Convert GBR to SVG, parallelly
    logger.info("Converting GBR to SVG files. ")
    files_for_svg = [GBR_EDGE_CUTS]
    if (config.gbr_path / GBR_PTH).with_suffix(".gbr").exists():
        files_for_svg.append(GBR_PTH)
    if (config.gbr_path / GBR_NPTH).with_suffix(".gbr").exists():
        files_for_svg.append(GBR_NPTH)
    with Pool() as p:
        p.map(partial(gbr_to_svg_convert), files_for_svg)

    logger.info("Post-processing SVG files. ")
    # Get edge cuts SVG dimensions
    edge_svg_dimensions_data = ""
    with open(str((config.svg_path / GBR_EDGE_CUTS).with_suffix(".svg")), "rt") as handle:
        svg_data = handle.read().split("\n")
        edge_svg_dimensions_data = svg_data[1]
    # Remove frame from layers and possible edge cuts (when edges cross with holes)
    map_input_list = [GBR_EDGE_CUTS, GBR_PTH, GBR_NPTH]
    with Pool() as p:
        p.map(
            partial(
                correct_frame_in_svg,
                frame=edge_svg_dimensions_data,
            ),
            map_input_list,
        )

    if config.blendcfg["SETTINGS"]["USE_INKSCAPE"]:
        logger.info("Processing SVG files with Inkscape.")
        inkscape_path_union((config.svg_path / GBR_PTH).with_suffix(".svg"))
        inkscape_path_union((config.svg_path / GBR_NPTH).with_suffix(".svg"))


def do_generate_displacement_map_foundation() -> None:
    """Generate the displacement map foundation."""
    logger.info("Generating top and bottom displacement map foundation... ")
    map_input_list = [OUT_F_DISPMAP, OUT_B_DISPMAP]

    with Pool() as p:
        p.map(partial(generate_displacement_map_png), map_input_list)


def do_convert_layer_to_png() -> None:
    """Convert required layer gerber files to PNGs."""
    logger.info("Converting all layers to PNG. ")

    files_names_list = get_gerbers_to_convert_to_png()
    map_input_list = [(file, file, HEX_WHITE, "#000000ff") for file in files_names_list if "Fab" not in file]
    # Make silks and mask for dispmap
    map_input_list.extend(
        [
            (GBR_F_SILK, TMP_F_SILKS, HEX_BLACK, HEX_WHITE_ALPHA),
            (GBR_B_SILK, TMP_B_SILKS, HEX_BLACK, HEX_WHITE_ALPHA),
            (GBR_F_MASK, TMP_F_MASK, MASK_BG_COLOR, MASK_FG_COLOR_ALPHA),
            (GBR_B_MASK, TMP_B_MASK, MASK_BG_COLOR, MASK_FG_COLOR_ALPHA),
        ]
    )

    with Pool() as p:
        p.map(partial(gbr_png_convert), map_input_list)


def do_crop_pngs() -> None:
    """Crop generated PNGs based on trim data generated from edge cuts."""
    logger.info("Cropping all pngs. ")

    # Trim edge_cuts and get crop data for other layers
    crop_offset = get_edge_trim_data()
    logger.info(
        "Calculated crop: w=%d h=%d x=%d y=%d",
        crop_offset[0],
        crop_offset[1],
        crop_offset[2],
        crop_offset[3],
    )

    map_input_list = [file for file in config.png_path.iterdir() if file.is_file()]
    for file in map_input_list:
        crop_png(file, crop_offset)


def do_generate_displacement_maps() -> None:
    """Generate the displacement maps."""
    logger.info("Building displacement maps.")

    # Prepare transparent holes pngs
    copy_file((config.png_path / GBR_PTH).with_suffix(".png"), (config.png_path / TMP_ALPHAW_PTH).with_suffix(".png"))
    copy_file((config.png_path / GBR_NPTH).with_suffix(".png"), (config.png_path / TMP_ALPHAW_NPTH).with_suffix(".png"))
    wand_operation(TMP_ALPHAW_PTH, fuzz=75, transparency="white", blur=[1, 2])
    wand_operation(TMP_ALPHAW_NPTH, fuzz=75, transparency="white", blur=[1, 2])

    # Adding blur to dispmap
    wand_operation(OUT_F_DISPMAP, out_file=OUT_F_DISPMAP)
    wand_operation(OUT_B_DISPMAP, out_file=OUT_B_DISPMAP)

    # Prepare transparent masks pngs for silk cutout
    wand_operation(TMP_F_MASK, out_file=TMP_F_MASK_SILKS, transparency=MASK_BG_COLOR, fuzz=15)
    wand_operation(TMP_B_MASK, out_file=TMP_B_MASK_SILKS, transparency=MASK_BG_COLOR, fuzz=15)

    # Prepare transparent masks pngs
    wand_operation(TMP_F_MASK, out_file=TMP_F_MASK, transparency=MASK_FG_COLOR, fuzz=20)
    wand_operation(TMP_B_MASK, out_file=TMP_B_MASK, transparency=MASK_FG_COLOR, fuzz=20)
    wand_operation(TMP_F_MASK, out_file=TMP_F_MASK, transparency=MASK_BG_COLOR, alpha=0.3, fuzz=20)
    wand_operation(TMP_B_MASK, out_file=TMP_B_MASK, transparency=MASK_BG_COLOR, alpha=0.3, fuzz=20)

    # Prepare transparent silks pngs + set silks alpha
    prepare_silks(TMP_F_SILKS, out_file=TMP_F_SILKS, mask=TMP_F_MASK_SILKS)
    prepare_silks(TMP_B_SILKS, out_file=TMP_B_SILKS, mask=TMP_B_MASK_SILKS)

    # Put silks on dispmap
    png_list = [TMP_F_SILKS, TMP_F_MASK, TMP_ALPHAW_PTH, TMP_ALPHAW_NPTH]
    add_pngs(OUT_F_DISPMAP, png_list, out_file=OUT_F_DISPMAP)
    png_list = [TMP_B_SILKS, TMP_B_MASK, TMP_ALPHAW_PTH, TMP_ALPHAW_NPTH]
    add_pngs(OUT_B_DISPMAP, png_list, out_file=OUT_B_DISPMAP)
    wand_operation(OUT_F_DISPMAP, out_file=OUT_F_DISPMAP, blur=[0, 2])
    wand_operation(OUT_B_DISPMAP, out_file=OUT_B_DISPMAP, blur=[0, 2])


def get_gerbers_to_convert_to_png() -> List[str]:
    """Get a list of .gbr files that need to be converted to PNG."""
    # Prepare data to convert GBR -> SVG
    files_names_list: List[str] = []  # list of gbr files to convert
    for file in config.gbr_path.iterdir():
        if file.is_file():
            files_names_list.append(file.stem)

    # Check if all important data are present
    if GBR_EDGE_CUTS not in files_names_list:
        raise RuntimeError("Missing Edge_Cuts gerber file. Aborting.")

    return files_names_list


########################################


def get_alignment_layers(color: str) -> str:
    """Prepare command string with alignment layers to be exported with gerbv.

    The alignment layers are layers that are needed to definitively ensure the same export dimensions
    and layer placements across all layer exports.
    Takes color in hex format ('#DDBBCCAA' convention) as argument and uses it as alignment layers' foreground color.
    It should be matched to be the same as export's background color.
    """
    gbr_path = str(config.gbr_path) + "/"
    fg = "--foreground"
    return f"'{gbr_path}{GBR_F_MASK}.gbr' {fg}={color} '{gbr_path}{GBR_B_MASK}.gbr' {fg}={color} \
                '{gbr_path}{GBR_F_FAB}.gbr' {fg}={color} '{gbr_path}{GBR_B_FAB}.gbr' {fg}={color} \
                '{gbr_path}{GBR_F_SILK}.gbr' {fg}={color} '{gbr_path}{GBR_B_SILK}.gbr' {fg}={color} \
                '{gbr_path}{GBR_F_CU}.gbr' {fg}={color} '{gbr_path}{GBR_B_CU}.gbr' {fg}={color} \
                '{gbr_path}{GBR_EDGE_CUTS}.gbr' {fg}={color}"


def gbr_png_convert(data: Tuple[str, str, str, str]) -> None:
    """Convert gerber file to png with given input name, output name, background and foreground."""
    gbr_file_name = data[0] + ".gbr"
    png_file_name = data[1] + ".png"

    in_gbr_file_path = config.gbr_path / gbr_file_name
    png_path = config.png_path / png_file_name

    bg_color = data[2]
    fg_color = data[3]
    fg = "--foreground"
    rc = os.system(
        f"gerbv '{in_gbr_file_path}' --background={bg_color} {fg}={fg_color} \
        {get_alignment_layers(HEX_BLACK_ALPHA)} \
        -o '{png_path}' --dpi={config.blendcfg['SETTINGS']['DPI']} -a --export=png 2>/dev/null"
    )
    if rc != 0:
        raise RuntimeError(f"Failed to convert Gerbers to PNG: gerbv returned exit code {rc}")


def generate_displacement_map_png(filename: str) -> None:
    """Prepare displacement map from PNGs."""
    gbr_path = str(config.gbr_path)
    png_path = (config.png_path / filename).with_suffix(".png")
    side = filename[0]  # first letter from png name
    fg = "--foreground"
    rc = os.system(
        f"gerbv '{gbr_path}{GBR_PTH}.gbr' --background=#555555 {fg}=#000000ff \
        '{gbr_path}{GBR_NPTH}.gbr' {fg}=#000000ff \
        '{gbr_path}{side}_Cu.gbr' {fg}=#808080ff \
        {get_alignment_layers(HEX_BLACK_ALPHA)} \
        -o '{png_path}' -a --dpi={config.blendcfg['SETTINGS']['DPI']} --export=png 2> /dev/null"
    )
    if rc != 0:
        raise RuntimeError(f"Failed to generate displacement map: gerbv returned exit code {rc}")


def copy_file(old_file_path: Path, new_file_path: Path) -> None:
    """Copy file from on path to other path with new name."""
    if old_file_path.exists():
        shutil.copy(old_file_path, new_file_path)
        os.sync()


def remove_files_with_ext(dir_path: Path, ext: str) -> None:
    """Remove files with given extension from given path."""
    for file in dir_path.iterdir():
        if file.suffix == ext:
            file.unlink()


def gbr_to_svg_convert(file_name: str) -> None:
    """Convert gerber file to svg."""
    gbr_file_path = (config.gbr_path / file_name).with_suffix(".gbr")
    svg_file_path = (config.svg_path / file_name).with_suffix(".svg")

    if not gbr_file_path.is_file():
        raise RuntimeError(f"Gerber file {str(gbr_file_path)} does not exist!")

    gerbv_command = f"gerbv '{str(gbr_file_path)}' --foreground={HEX_BLACK} \
    '{str(config.gbr_path)}/{GBR_NPTH}.gbr' --foreground={HEX_WHITE} \
    '{str(config.gbr_path)}/{GBR_PTH}.gbr' --foreground={HEX_WHITE} \
    '{str(config.gbr_path)}/{GBR_EDGE_CUTS}.gbr' --foreground={HEX_WHITE} \
    -o '{str(svg_file_path)}' --export=svg 2>/dev/null"
    rc = os.system(gerbv_command)
    if rc != 0:
        raise RuntimeError(f"Failed to convert Gerbers to SVG: gerbv returned exit code {rc}")

    # patch for gerbv<2.10.1 & cairo > 1.17.6
    original_svg = svg_file_path.read_text()
    svg_w_units = re.sub(r'width="(\d*)" height="(\d*)"', r'width="\1pt" height="\2pt"', original_svg)
    svg_file_path.write_text(svg_w_units)


def correct_frame_in_svg(data: str, frame: str) -> None:
    """Correct dimension of svg file based on edge cuts layer."""
    file_path = (config.svg_path / data).with_suffix(".svg")
    if not file_path.exists():
        return
    with open(file_path, "rt") as handle:
        svg_data = handle.read().split("\n")

    if len(svg_data) < 2:
        return

    svg_data[1] = frame
    corrected_svg = [line for line in svg_data if "rgb(100%,100%,100%)" not in line]
    with open(file_path, "wt") as handle:
        handle.write("\n".join(corrected_svg))


def inkscape_path_union(file_path: Path) -> None:
    """Run Inkscape command."""
    if not file_path.exists():
        return
    inkscape_actions = "select-all;object-stroke-to-path;path-union;"
    rc = os.system(
        f'inkscape --actions="{inkscape_actions}export-filename:{str(file_path)};export-do" "{str(file_path)}"'
    )

    if rc != 0:
        raise RuntimeError(f"Failed to generate path union: inkscape returned exit code {rc}")


def get_edge_trim_data() -> List[int]:
    """Calculate trim offset for PNGs."""
    with Image(filename=str((config.png_path / GBR_EDGE_CUTS).with_suffix(".png"))) as edge_cuts_png:
        edge_cuts_png.trim(percent_background=0.98)

        count_edge = 0
        for i in range(edge_cuts_png.width):
            pix = edge_cuts_png[i, int(edge_cuts_png.height / 2)]
            if pix == Color("white"):
                break
            count_edge += 1

        shave_offset = int(count_edge / 2)
        return [
            edge_cuts_png.width - count_edge,
            edge_cuts_png.height - count_edge,
            edge_cuts_png.page_x + shave_offset,
            edge_cuts_png.page_y + shave_offset,
        ]


def crop_png(image_path: Path, crop_offset: List[int]) -> None:
    """Crop PNG using calculated offset."""
    with Image(filename=str(image_path)) as png:
        image_width = png.width
        image_height = png.height
        if image_width < crop_offset[0] + crop_offset[2]:
            logger.warning(image_path, image_width, image_height)
            logger.warning(crop_offset[0] + crop_offset[2])
            logger.warning("Image to crop is thinner than given crop values.")
            return
        if image_height < crop_offset[1] + crop_offset[3]:
            logger.warning(image_path)
            logger.warning(crop_offset[1] + crop_offset[3])
            logger.warning("Image to crop is higher than given crop values.")
            return

        png.crop(
            width=crop_offset[0],
            height=crop_offset[1],
            left=crop_offset[2],
            top=crop_offset[3],
        )
        png.save(filename=str(image_path))


def wand_operation(
    in_file: str,
    out_file: str = "",
    fuzz: int = 0,
    transparency: str = "",
    alpha: float = 0.0,
    blur: None | List[int] = None,
) -> None:
    """Imagemagick-like operation."""
    image_path = (config.png_path / in_file).with_suffix(".png")
    if not image_path.exists():
        return
    with Image(filename=str(image_path)) as png:
        percent_fuzz = int(png.quantum_range * fuzz / 100)
        if transparency != "":
            png.transparent_color(color=Color(transparency), alpha=alpha, fuzz=percent_fuzz)
        if blur is not None:
            png.blur(blur[0], blur[1])
        if out_file == "":
            out_file = in_file
        png.save(filename=f"{str(config.png_path)}/{out_file}.png")


def add_pngs(in_file: str, in_list: List[str], out_file: str = "") -> None:
    """Join PNGs on one another."""
    if out_file == "":
        out_file = in_file
    with Image(filename=f"{config.png_path}/{in_file}.png") as png:
        png.background_color = Color("transparent")
        for file in in_list:
            file_path = (config.png_path / file).with_suffix(".png")
            if not file_path.exists():
                continue
            with Image(filename=str(file_path)) as png2:
                png2.transparent_color(color=Color("white"), alpha=0.0)
                png.composite(image=png2, gravity="center")
        png.save(filename=f"{config.png_path}/{out_file}.png")


def prepare_silks(in_file: str, mask: str = "", out_file: str = "") -> None:
    """Cutout mask areas + prepare transparent silks pngs + set silks alpha."""
    if out_file == "":
        out_file = in_file
    with Image(filename=f"{config.png_path}/{in_file}.png") as png:
        if mask != "":
            with Image(filename=f"{config.png_path}/{mask}.png") as png2:
                png2.colorize(color=Color("black"), alpha=Color(MASK_FG_COLOR))
                png.composite(image=png2, gravity="center")
        png.transparent_color(color=Color("black"), alpha=0.0)
        levelize_matrix = [
            [1, 0, 0, 0, 1],
            [0, 1, 0, 0, 1],
            [0, 0, 1, 0, 1],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0.5],
        ]
        png.color_matrix(levelize_matrix)
        png.save(filename=f"{config.png_path}/{out_file}.png")


def prepare_solder() -> None:
    """Prepare PNG with Solder placements."""
    if config.blendcfg["EFFECTS"]["SOLDER"]:
        logger.info("Generate PNGs with solder placement")
        prepare_solder_side(GBR_F_CU, GBR_F_MASK, GBR_F_PASTE, OUT_F_SOLDER)
        prepare_solder_side(GBR_B_CU, GBR_B_MASK, GBR_B_PASTE, OUT_B_SOLDER)


def prepare_solder_side(gbr_cu: str, gbr_mask: str, gbr_paste: str, gbr_out: str) -> None:
    """Prepare PNG with Solder placement on single board side."""
    cu = (config.png_path / gbr_cu).with_suffix(".png")
    mask = (config.png_path / gbr_mask).with_suffix(".png")
    paste = (config.png_path / gbr_paste).with_suffix(".png")
    ofile = (config.png_path / gbr_out).with_suffix(".png")
    ofile_fixer = (config.png_path / f"{gbr_out}_fixer").with_suffix(".png")
    ofile_svg = (config.svg_path / gbr_out).with_suffix(".svg")
    ofile_fixer_svg = (config.svg_path / f"{gbr_out}_fixer").with_suffix(".svg")
    if not paste.exists():
        return

    with Image(filename=str(cu)) as cu, Image(filename=str(mask)) as mask, Image(filename=str(paste)) as paste:
        assert isinstance(cu, Image)
        assert isinstance(paste, Image)

        cu.composite(image=mask, gravity="center", operator="lighten")
        cu.composite(image=mask, gravity="center", operator="lighten")
        cu.threshold(0.5)

        cu.negate()
        paste.negate()
        paste2 = paste.clone()
        paste2.morphology(method="dilate", kernel="disk:30", iterations=1)
        paste2.morphology(method="erode", kernel="disk:28", iterations=1)
        for _ in range(10):
            paste.morphology(method="dilate", kernel="disk", iterations=1)
            paste.composite(image=cu, gravity="center", operator="darken")
        paste.composite(image=paste2, gravity="center", operator="darken")
        paste.morphology(method="dilate", kernel="disk:1", iterations=1)
        paste.negate()
        paste.threshold(0.1)

        paste.save(filename=str(ofile))

        paste.morphology(method="erode", kernel="disk:2", iterations=1)
        paste.save(filename=str(ofile_fixer))

        vtracer.convert_image_to_svg_py(str(ofile), str(ofile_svg), colormode="binary", hierarchical="cutout")
        vtracer.convert_image_to_svg_py(
            str(ofile_fixer), str(ofile_fixer_svg), colormode="binary", hierarchical="cutout"
        )
