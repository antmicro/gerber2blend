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
import gerber2blend.core.blendcfg
import gerber2blend.modules.config as config
import gerber2blend.modules.file_io as fio
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
    mkdir(config.svg_path)
    mkdir(config.png_path)
    mkdir(config.gbr_path)

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
                new_path = config.gbr_path + gerb_file_renames[k] + ".gbr"
                logger.info("Gerber file %s missing. Replacing with empty file: %s", k, new_path)
                fio.touch(new_path)
            continue

        logger.info("Looking up %s in %s..", v, config.fab_path)
        fpath = os.path.join(config.fab_path, v)
        matches = glob.glob(fpath)
        if len(matches) == 0:
            if gerber2blend.core.blendcfg.CONFIGURATION_SCHEMA["GERBER_FILENAMES"][k].optional:
                logger.warning(f"Did not find optional {k} in path: {config.fab_path}")
            else:
                logger.error(
                    "Could not find required Gerber %s with pattern: %s in %s/ directory!",
                    k,
                    v,
                    gbr_dir,
                )
                gerbers_missing = True
            continue

        # Handle inputs with many files
        if k in gerbs_with_many_files:
            # Sort the filelist, as glob.glob() does not guarantee a sorted output
            matches = sorted(
                matches,
                key=lambda x: int(x.split("/")[-1].split("-In")[-1].replace("_Cu.gbr", "")),
            )
            if len(matches) == 0:
                logger.error(
                    "Could not find required Gerber %s with pattern: %s in %s/ directory!",
                    k,
                    v,
                    gbr_dir,
                )
                gerbers_missing = True
            for i in range(0, len(matches)):
                gerber_path = matches[i]
                new_name = gerb_file_renames[k] + str(i) + ".gbr"
                new_path = config.gbr_path + new_name
                logger.info("Found %s%d: %s, saving as: %s", k, i, gerber_path, new_path)
                shutil.copy(gerber_path, new_path)
            continue

        gerber_path = matches[0]
        new_name = gerb_file_renames[k] + ".gbr"
        new_path = config.gbr_path + new_name

        logger.info("Found %s: %s, saving as: %s", k, gerber_path, new_path)
        shutil.copy(gerber_path, new_path)

    if gerbers_missing:
        raise RuntimeError(f"One or more mandatory Gerber files are missing from the {gbr_dir}/ directory.")


def do_convert_gerb_to_svg() -> None:
    """Convert required gerb files to SVG."""
    # Convert GBR to SVG, parallelly
    logger.info("Converting GBR to SVG files. ")
    files_for_svg = [GBR_EDGE_CUTS]
    if os.path.exists(os.path.join(config.gbr_path, GBR_PTH + ".gbr")):
        files_for_svg.append(GBR_PTH)
    if os.path.exists(os.path.join(config.gbr_path, GBR_NPTH + ".gbr")):
        files_for_svg.append(GBR_NPTH)
    with Pool() as p:
        p.map(partial(gbr_to_svg_convert), files_for_svg)

    logger.info("Post-processing SVG files. ")
    # Get edge cuts SVG dimensions
    edge_svg_dimensions_data = ""
    with open(f"{config.svg_path}{GBR_EDGE_CUTS}.svg", "rt") as handle:
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
        inkscape_path_union(f"{config.svg_path}{GBR_PTH}.svg")
        inkscape_path_union(f"{config.svg_path}{GBR_NPTH}.svg")


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

    map_input_list = [file for file in os.listdir(config.png_path) if os.path.isfile(config.png_path + file)]
    for file in map_input_list:
        crop_png(file, crop_offset)


def do_generate_displacement_maps() -> None:
    """Generate the displacement maps."""
    logger.info("Building displacement maps.")

    # Prepare transparent holes pngs
    copy_file(config.png_path, config.png_path, GBR_PTH + ".png", TMP_ALPHAW_PTH + ".png")
    copy_file(config.png_path, config.png_path, GBR_NPTH + ".png", TMP_ALPHAW_NPTH + ".png")
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
    files_names_list = list()  # list of gbr files to convert;
    for file in os.listdir(config.gbr_path):
        if os.path.isfile(config.gbr_path + file):
            files_names_list.append(file.replace(".gbr", ""))

    # Check if all important data are present
    if GBR_EDGE_CUTS not in files_names_list:
        raise RuntimeError("Missing Edge_Cuts gerber file. Aborting.")

    return files_names_list


########################################


def gbr_png_convert(data: Tuple[str, str, str, str]) -> None:
    """Convert gerber file to png with given input name, output name, background and foreground."""
    gbr_file_name = data[0] + ".gbr"
    png_file_name = data[1] + ".png"

    gbr_path = config.gbr_path
    in_gbr_file_path = os.path.join(config.gbr_path, gbr_file_name)
    png_path = os.path.join(config.png_path, png_file_name)

    bg_color = data[2]
    fg_color = data[3]
    fg = "--foreground"
    # All data are present in gerbv convert function to ensure the same size of all converted PNGs
    rc = os.system(
        f"gerbv {in_gbr_file_path} --background={bg_color} {fg}={fg_color} \
        {gbr_path}{GBR_F_MASK}.gbr {fg}={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_MASK}.gbr {fg}={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_FAB}.gbr {fg}={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_FAB}.gbr {fg}={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_SILK}.gbr {fg}={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_SILK}.gbr {fg}={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_EDGE_CUTS}.gbr {fg}={HEX_BLACK_ALPHA} \
        -o {png_path} --dpi={config.blendcfg['SETTINGS']['DPI']} -a --export=png 2>/dev/null"
    )
    if rc != 0:
        raise RuntimeError(f"Failed to convert Gerbers to PNG: gerbv returned exit code {rc}")


def generate_displacement_map_png(filename: str) -> None:
    """Prepare displacement map from PNGs."""
    gbr_path = config.gbr_path
    png_path = os.path.join(config.png_path, filename + ".png")
    side = filename[0]  # first letter from png name
    fg = "--foreground"
    rc = os.system(
        f"gerbv {gbr_path}{GBR_PTH}.gbr --background=#555555 {fg}=#000000ff \
        {gbr_path}{GBR_NPTH}.gbr {fg}=#000000ff \
        {gbr_path}{side}_Cu.gbr {fg}=#808080ff \
        {gbr_path}{GBR_F_MASK}.gbr {fg}={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_MASK}.gbr {fg}={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_FAB}.gbr {fg}={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_FAB}.gbr {fg}={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_SILK}.gbr {fg}={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_SILK}.gbr {fg}={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_EDGE_CUTS}.gbr {fg}={HEX_BLACK_ALPHA} \
        -o {png_path} -a --dpi={config.blendcfg['SETTINGS']['DPI']} --export=png 2> /dev/null"
    )
    if rc != 0:
        raise RuntimeError(f"Failed to generate displacement map: gerbv returned exit code {rc}")


def mkdir(path: str) -> None:
    """Create a directory at the specified path.

    Wraps any errors with a nicer error exception.
    """
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Could not create folder at path {path}: {repr(e)}") from e


def copy_file(path: str, new_path: str, old_file_name: str, new_file_name: str) -> None:
    """Copy file from on path to other path with new name."""
    if os.path.exists(path + old_file_name):
        shutil.copy(path + old_file_name, new_path + new_file_name)
        os.sync()


def remove_files_with_ext(path: str, ext: str) -> None:
    """Remove files with given extension from given path."""
    file_list = [file for file in os.listdir(path) if file.endswith(ext)]
    for file in file_list:
        os.remove(path + file)


def gbr_to_svg_convert(file_name: str) -> None:
    """Convert gerber file to svg."""
    gbr_path = config.gbr_path
    svg_path = config.svg_path
    gbr_file_path = os.path.join(gbr_path, file_name + ".gbr")
    svg_file_path = os.path.join(svg_path, file_name + ".svg")

    if not os.path.isfile(gbr_file_path):
        raise RuntimeError(f"Gerber file {gbr_file_path} does not exist!")

    gerbv_command = f"gerbv {gbr_file_path} --foreground={HEX_BLACK} \
    {gbr_path}{GBR_EDGE_CUTS}.gbr --foreground={HEX_WHITE} \
    -o {svg_file_path} --export=svg 2>/dev/null"
    rc = os.system(gerbv_command)
    if rc != 0:
        raise RuntimeError(f"Failed to convert Gerbers to SVG: gerbv returned exit code {rc}")

    # patch for gerbv<2.10.1 & cairo > 1.17.6
    original_svg = Path(svg_file_path).read_text()
    svg_w_units = re.sub(r'width="(\d*)" height="(\d*)"', r'width="\1pt" height="\2pt"', original_svg)
    Path(svg_file_path).write_text(svg_w_units)


def correct_frame_in_svg(data: str, frame: str) -> None:
    """Correct dimension of svg file based on edge cuts layer."""
    file_path = config.svg_path + data + ".svg"
    if not os.path.exists(file_path):
        return
    with open(file_path, "rt") as handle:
        svg_data = handle.read().split("\n")

    if len(svg_data) < 2:
        return

    svg_data[1] = frame
    corrected_svg = [line for line in svg_data if "rgb(100%,100%,100%)" not in line]
    with open(file_path, "wt") as handle:
        handle.write("\n".join(corrected_svg))


def inkscape_path_union(file_path: str) -> None:
    """Run Inkscape command."""
    if not os.path.exists(file_path):
        return
    inkscape_actions = "select-all;object-stroke-to-path;path-union;"
    rc = os.system(f'inkscape --actions="{inkscape_actions}export-filename:{file_path};export-do" {file_path}')

    if rc != 0:
        raise RuntimeError(f"Failed to generate path union: inkscape returned exit code {rc}")


def get_edge_trim_data() -> List[int]:
    """Calculate trim offset for PNGs."""
    with Image(filename=os.path.join(config.png_path, GBR_EDGE_CUTS + ".png")) as edge_cuts_png:
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


def crop_png(file: str, crop_offset: List[int]) -> None:
    """Crop PNG using calculated offset."""
    image_path = os.path.join(config.png_path, file)

    with Image(filename=image_path) as png:
        image_width = png.width
        image_height = png.height
        if image_width < crop_offset[0] + crop_offset[2]:
            logger.warn("%d", crop_offset[0] + crop_offset[2])
            logger.warn("Image to crop is thinner than given crop values.")
            return
        if image_height < crop_offset[1] + crop_offset[3]:
            logger.warn("%d", crop_offset[1] + crop_offset[3])
            logger.warn("Image to crop is higher than given crop values.")
            return

        png.crop(
            width=crop_offset[0],
            height=crop_offset[1],
            left=crop_offset[2],
            top=crop_offset[3],
        )
        png.save(filename=image_path)


def wand_operation(
    in_file: str,
    out_file: str = "",
    fuzz: int = 0,
    transparency: str = "",
    alpha: float = 0.0,
    blur: None | List[int] = None,
) -> None:
    """Imagemagick-like operation."""
    image_path = config.png_path + in_file + ".png"
    if not os.path.exists(image_path):
        return
    with Image(filename=image_path) as png:
        percent_fuzz = int(png.quantum_range * fuzz / 100)
        if transparency != "":
            png.transparent_color(color=Color(transparency), alpha=alpha, fuzz=percent_fuzz)
        if blur is not None:
            png.blur(blur[0], blur[1])
        if out_file == "":
            out_file = in_file
        png.save(filename=config.png_path + out_file + ".png")


def add_pngs(in_file: str, in_list: List[str], out_file: str = "") -> None:
    """Join PNGs on one another."""
    if out_file == "":
        out_file = in_file
    with Image(filename=config.png_path + in_file + ".png") as png:
        png.background_color = Color("transparent")
        for file in in_list:
            file_path = config.png_path + file + ".png"
            if not os.path.exists(file_path):
                continue
            with Image(filename=file_path) as png2:
                png2.transparent_color(color=Color("white"), alpha=0.0)
                png.composite(image=png2, gravity="center")
        png.save(filename=config.png_path + out_file + ".png")


def prepare_silks(in_file: str, mask: str = "", out_file: str = "") -> None:
    """Cutout mask areas + prepare transparent silks pngs + set silks alpha."""
    if out_file == "":
        out_file = in_file
    with Image(filename=config.png_path + in_file + ".png") as png:
        if mask != "":
            with Image(filename=config.png_path + mask + ".png") as png2:
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
        png.save(filename=config.png_path + out_file + ".png")


def prepare_solder() -> None:
    """Prepare PNG with Solder placements."""
    if config.solder:
        logger.info("Generate PNGs with solder placement")
        prepare_solder_side(GBR_F_CU, GBR_F_MASK, GBR_F_PASTE, OUT_F_SOLDER)
        prepare_solder_side(GBR_B_CU, GBR_B_MASK, GBR_B_PASTE, OUT_B_SOLDER)


def prepare_solder_side(cu: str, mask: str, paste: str, out: str) -> None:
    """Prepare PNG with Solder placement on single board side."""
    cu = config.png_path + cu + ".png"
    mask = config.png_path + mask + ".png"
    paste = config.png_path + paste + ".png"
    ofile = config.png_path + out + ".png"
    ofilesvg = config.svg_path + out + ".svg"
    if not os.path.exists(paste):
        return

    with Image(filename=cu) as cu, Image(filename=mask) as mask, Image(filename=paste) as paste:
        assert type(cu) == Image
        assert type(paste) == Image

        cu.composite(image=mask, gravity="center", operator="lighten")
        cu.composite(image=mask, gravity="center", operator="lighten")
        cu.threshold(0.5)

        cu.negate()
        paste.negate()
        for i in range(10):
            paste.morphology(method="dilate", kernel="disk", iterations=1)
            paste.composite(image=cu, gravity="center", operator="darken")
        paste.morphology(method="dilate", kernel="disk:1", iterations=1)
        paste.negate()
        paste.threshold(0.1)

        paste.save(filename=ofile)

        vtracer.convert_image_to_svg_py(ofile, ofilesvg, colormode="binary", hierarchical="cutout")
