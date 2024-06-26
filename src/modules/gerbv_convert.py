#!/bin/python3
import os
import shutil
import logging
import glob
from functools import partial
from multiprocessing import Pool
from typing import List, Tuple
from wand.image import Image  # type: ignore
from wand.color import Color  # type: ignore
import core.module
import modules.config as config
from modules.config import (
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
TMP_ALPHAW_PTH = "alphaw-PTH-drl"
TMP_ALPHAW_NPTH = "alphaw-NPTH-drl"
TMP_ALPHAB_F_MASK = "alphab-F_Mask"
TMP_ALPHAB_B_MASK = "alphab-B_Mask"

logger = logging.getLogger(__name__)


class GerbConvert(core.module.Module):
    """Module to convert gerbers to the required intermediate files"""

    def execute(self):
        """Run the module"""

        do_prepare_build_directory()
        do_convert_gerb_to_svg()
        do_generate_displacement_map_foundation()
        do_convert_layer_to_png()
        do_crop_pngs()
        do_generate_displacement_maps()


def do_prepare_build_directory():
    """Prepare the build directory and populate it with required files"""
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
    GERB_FILE_RENAMES = {
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
    }
    # Inputs that are allowed to have many files.
    # For each matching input file, the file will be copied to
    # the fab/GBR/ directory under the name:
    #   GERB_FILE_RENAMES[which_input] + <index_of_file> + ".gbr"
    # The files are indexed according to the lexicographical order of
    # their original file names.
    GERBS_WITH_MANY_FILES = [
        "IN",
    ]

    # Check all of the filenames specified in "GERBER_FILENAMES" and
    # move them to the build directory under the above specified names.
    gerbers_missing = False
    for k, v in config.blendcfg["GERBER_FILENAMES"].items():
        logger.info("Looking up %s in %s..", v, config.path)
        fpath = os.path.join(config.path, v)
        matches = glob.glob(fpath)
        if len(matches) == 0:
            logger.error(
                "Could not find required Gerber %s with pattern: %s in fab/ directory!",
                k,
                v,
            )
            gerbers_missing = True
            continue

        # Handle inputs with many files
        if k in GERBS_WITH_MANY_FILES:
            # Sort the filelist, as glob.glob() does not guarantee a sorted output
            matches = sorted(matches)
            for i in range(0, len(matches)):
                gerber_path = matches[i]
                new_name = GERB_FILE_RENAMES[k] + str(i) + ".gbr"
                new_path = config.gbr_path + new_name
                logger.info(
                    "Found %s%d: %s, saving as: %s", k, i, gerber_path, new_path
                )
                shutil.copy(gerber_path, new_path)
            continue

        gerber_path = matches[0]
        new_name = GERB_FILE_RENAMES[k] + ".gbr"
        new_path = config.gbr_path + new_name

        logger.info("Found %s: %s, saving as: %s", k, gerber_path, new_path)
        shutil.copy(gerber_path, new_path)

    if gerbers_missing:
        raise RuntimeError(
            "One or more Gerber files are missing from the fab/ directory. "
        )


def do_convert_gerb_to_svg():
    """Convert required gerb files to SVG"""

    # Convert GBR to SVG, parallelly
    logger.info("Converting GBR to SVG files. ")
    files_for_SVG = [GBR_PTH, GBR_NPTH, GBR_EDGE_CUTS]
    with Pool() as p:
        p.map(partial(gbr_to_svg_convert), files_for_SVG)

    logger.info("Post-processing SVG files. ")
    # Get edge cuts SVG dimensions
    edge_svg_dimensions_data = ""
    with open(f"{config.svg_path}{GBR_EDGE_CUTS}.svg", "rt") as handle:
        svg_data = handle.read().split("\n")
        edge_svg_dimensions_data = svg_data[1]
        edge_cuts_lines = [line for line in svg_data if "<path" in line]

    # Remove frame from layers
    map_input_list = [GBR_PTH, GBR_NPTH]
    with Pool() as p:
        p.map(
            partial(
                correct_frame_in_svg,
                frame=edge_svg_dimensions_data,
                frame_lines=edge_cuts_lines,
            ),
            map_input_list,
        )

    if config.blendcfg["SETTINGS"]["USE_INKSCAPE"]:
        logger.info("Processing SVG files with Inkscape.")
        inkscape_path_union(f"{config.svg_path}{GBR_PTH}.svg")
        inkscape_path_union(f"{config.svg_path}{GBR_NPTH}.svg")


def do_generate_displacement_map_foundation():
    """Generate the displacement map foundation"""
    logger.info("Generating top and bottom displacement map foundation... ")
    map_input_list = [OUT_F_DISPMAP, OUT_B_DISPMAP]

    with Pool() as p:
        p.map(partial(generate_displacement_map_png), map_input_list)


def do_convert_layer_to_png():
    """Convert required layer gerber files to PNGs"""
    logger.info("Converting all layers to PNG. ")

    files_names_list = get_gerbers_to_convert_to_png()
    map_input_list = [
        [file, file, HEX_WHITE, "#000000ff"]
        for file in files_names_list
        if "Fab" not in file
    ]
    # Make silks and mask for dispmap
    map_input_list.extend(
        [
            (GBR_F_SILK, TMP_F_SILKS, HEX_BLACK, HEX_WHITE_ALPHA),
            (GBR_B_SILK, TMP_B_SILKS, HEX_BLACK, HEX_WHITE_ALPHA),
            (GBR_F_MASK, TMP_F_MASK, HEX_BLACK, "#404040ff"),
            (GBR_B_MASK, TMP_B_MASK, HEX_BLACK, "#404040ff"),
        ]
    )

    with Pool() as p:
        p.map(partial(gbr_png_convert), map_input_list)


def do_crop_pngs():
    """Crop generated PNGs based on trim data generated from edge cuts"""
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

    map_input_list = [
        file
        for file in os.listdir(config.png_path)
        if os.path.isfile(config.png_path + file)
    ]
    for file in map_input_list:
        crop_png(file, crop_offset)


def do_generate_displacement_maps():
    """Generate the displacement maps"""
    logger.info("Building displacement maps.")

    # Prepare transparent holes pngs
    copy_file(
        config.png_path, config.png_path, GBR_PTH + ".png", TMP_ALPHAW_PTH + ".png"
    )
    copy_file(
        config.png_path, config.png_path, GBR_NPTH + ".png", TMP_ALPHAW_NPTH + ".png"
    )
    wand_operation(TMP_ALPHAW_PTH, fuzz=75, transparency="white", blur=[1, 8])
    wand_operation(TMP_ALPHAW_NPTH, fuzz=75, transparency="white", blur=[1, 8])

    # Prepare transparent mask pngs
    wand_operation(
        GBR_F_MASK, out_file=TMP_ALPHAB_F_MASK, fuzz=75, transparency="black"
    )
    wand_operation(
        GBR_B_MASK, out_file=TMP_ALPHAB_B_MASK, fuzz=75, transparency="black"
    )
    wand_operation(TMP_F_MASK, transparency="black", blur=[0, 3])
    wand_operation(TMP_B_MASK, transparency="black", blur=[0, 3])

    # Adding blur to dispmap
    wand_operation(OUT_F_DISPMAP, blur=[0, 6])
    wand_operation(OUT_B_DISPMAP, blur=[0, 6])

    # Prepare transparent silks pngs + set silks alpha
    prepare_silks(TMP_F_SILKS, TMP_F_SILKS)
    prepare_silks(TMP_B_SILKS, TMP_B_SILKS)

    # Put silks on dispmap
    png_list = [TMP_F_SILKS, TMP_F_MASK, TMP_ALPHAW_PTH, TMP_ALPHAW_NPTH]
    add_pngs(OUT_F_DISPMAP, png_list, out=OUT_F_DISPMAP)
    png_list = [TMP_B_SILKS, TMP_B_MASK, TMP_ALPHAW_PTH, TMP_ALPHAW_NPTH]
    add_pngs(OUT_B_DISPMAP, png_list, out=OUT_B_DISPMAP)


def get_gerbers_to_convert_to_png():
    """Get a list of .gbr files that need to be converted to PNG"""
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


def gbr_png_convert(data: Tuple[str, str, str, str]):
    """Convert gerber file to png with given input name, output name, background and foreground"""

    gbr_file_name = data[0] + ".gbr"
    png_file_name = data[1] + ".png"

    gbr_path = config.gbr_path
    in_gbr_file_path = os.path.join(config.gbr_path, gbr_file_name)
    png_path = os.path.join(config.png_path, png_file_name)

    bg = data[2]
    fg = data[3]
    # All data are present in gerbv convert function to ensure the same size of all converted PNGs
    rc = os.system(
        f"gerbv {in_gbr_file_path} --background={bg} --foreground={fg} \
        {gbr_path}{GBR_F_MASK}.gbr --foreground={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_MASK}.gbr --foreground={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_FAB}.gbr --foreground={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_FAB}.gbr --foreground={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_SILK}.gbr --foreground={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_SILK}.gbr --foreground={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_EDGE_CUTS}.gbr --foreground={HEX_BLACK_ALPHA} \
        -o {png_path} --dpi={config.blendcfg['SETTINGS']['DPI']} -a --export=png 2>/dev/null"
    )
    if rc != 0:
        raise RuntimeError(
            f"Failed to convert Gerbers to PNG: gerbv returned exit code {rc}"
        )


def generate_displacement_map_png(filename: str):
    """Prepare displacement map from PNGs"""

    gbr_path = config.gbr_path
    png_path = os.path.join(config.png_path, filename + ".png")
    side = filename[0]  # first letter from png name
    rc = os.system(
        f"gerbv {gbr_path}{GBR_PTH}.gbr --background=#555555 --foreground=#000000ff \
        {gbr_path}{GBR_NPTH}.gbr --foreground=#000000ff \
        {gbr_path}{side}_Mask.gbr --foreground=#404040ff \
        {gbr_path}{side}_Cu.gbr --foreground=#888888ff \
        {gbr_path}{GBR_F_MASK}.gbr --foreground={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_MASK}.gbr --foreground={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_FAB}.gbr --foreground={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_FAB}.gbr --foreground={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_F_SILK}.gbr --foreground={HEX_BLACK_ALPHA} {gbr_path}{GBR_B_SILK}.gbr --foreground={HEX_BLACK_ALPHA} \
        {gbr_path}{GBR_EDGE_CUTS}.gbr --foreground={HEX_BLACK_ALPHA} \
        -o {png_path} -a --dpi={config.blendcfg['SETTINGS']['DPI']} --export=png 2> /dev/null"
    )
    if rc != 0:
        raise RuntimeError(
            f"Failed to generate displacement map: gerbv returned exit code {rc}"
        )


def mkdir(path: str):
    """Create a directory at the specified path

    Wraps any errors with a nicer error exception.
    """
    try:
        os.makedirs(path, exist_ok=True)
    except OSError as e:
        raise RuntimeError(f"Could not create folder at path {path}: {repr(e)}")


def copy_file(path: str, new_path: str, old_file_name: str, new_file_name: str):
    """Copy file from on path to other path with new name"""

    if os.path.exists(path + old_file_name):
        shutil.copy(path + old_file_name, new_path + new_file_name)
        os.sync()


def remove_files_with_ext(path: str, ext: str):
    """Remove files with given extension from given path"""
    file_list = [file for file in os.listdir(path) if file.endswith(ext)]
    for file in file_list:
        os.remove(path + file)


def gbr_to_svg_convert(file_name: str):
    """Convert gerber file to svg"""
    gbr_path = config.gbr_path
    svg_path = config.svg_path
    gbr_file_path = os.path.join(gbr_path, file_name + ".gbr")
    svg_file_path = os.path.join(svg_path, file_name + ".svg")

    if not os.path.isfile(gbr_file_path):
        raise RuntimeError(f"Gerber file {gbr_file_path} does not exist!")

    rc = os.system(
        f"gerbv {gbr_file_path} --foreground={HEX_BLACK} \
        {gbr_path}{GBR_EDGE_CUTS}.gbr --foreground={HEX_BLACK_ALPHA} \
        -o {svg_file_path} --export=svg 2>/dev/null"
    )
    if rc != 0:
        raise RuntimeError(
            f"Failed to convert Gerbers to SVG: gerbv returned exit code {rc}"
        )


def correct_frame_in_svg(data, frame, frame_lines):
    """Correct dimension of svg file based on edge cuts layer"""
    file_path = config.svg_path + data + ".svg"
    with open(file_path, "rt") as handle:
        svg_data = handle.read().split("\n")

    if len(svg_data) < 2:
        return

    svg_data[1] = frame
    corrected_svg = [line for line in svg_data if line not in frame_lines]
    with open(file_path, "wt") as handle:
        handle.write("\n".join(corrected_svg))


def inkscape_path_union(file_path: str):
    """Run Inkscape command"""
    rc = os.system(
        f'inkscape --actions="select-all;object-stroke-to-path;path-union;export-filename:{file_path};export-do" {file_path}'
    )
    if rc != 0:
        raise RuntimeError(
            f"Failed to generate path union: inkscape returned exit code {rc}"
        )


def get_edge_trim_data() -> List[int]:
    """Calculate trim offset for PNGs"""

    with Image(
        filename=os.path.join(config.png_path, GBR_EDGE_CUTS + ".png")
    ) as edge_cuts_png:
        edge_cuts_png.trim()

        count_edge = 0
        for i in range(edge_cuts_png.width):
            pix = edge_cuts_png[i, int(edge_cuts_png.height / 2)]
            if pix == Color("white"):
                break
            count_edge += 1

        shave_offset = int(count_edge / 2)
        trims = [
            edge_cuts_png.width - 2 * shave_offset,
            edge_cuts_png.height - 2 * shave_offset,
            edge_cuts_png.page_x + shave_offset,
            edge_cuts_png.page_y + shave_offset,
        ]

        return trims


def crop_png(file: str, crop_offset: List[int]):
    """Crop PNG using calculated offset"""

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
            left=crop_offset[2],
            top=crop_offset[3],
            width=crop_offset[0],
            height=crop_offset[1],
        )
        png.save(filename=image_path)


def wand_operation(
    in_file: str,
    out_file: str = "",
    fuzz: int = 0,
    transparency: str = "",
    blur: List[int] = [],
):
    """Imagemagick-like operation"""

    image_path = config.png_path + in_file + ".png"

    with Image(filename=image_path) as png:
        percent_fuzz = int(png.quantum_range * fuzz / 100)
        if transparency is not None:
            png.transparent_color(
                color=Color(transparency), alpha=0.0, fuzz=percent_fuzz
            )
        if len(blur) >= 2:
            png.blur(blur[0], blur[1])
        if out_file is None:
            out_file = in_file
        png.save(filename=config.png_path + out_file + ".png")


def add_pngs(in1, in_list, out):
    """Join PNGs on one another"""

    with Image(filename=config.png_path + in1 + ".png") as png:
        png.background_color = Color("transparent")
        for file in in_list:
            with Image(filename=config.png_path + file + ".png") as png2:
                png.composite(image=png2, gravity="center")

        png.save(filename=config.png_path + out + ".png")


def prepare_silks(in_file, out_file):
    """Prepare transparent silks pngs + set silks alpha"""

    with Image(filename=config.png_path + in_file + ".png") as png:
        png.transparent_color(color=Color("black"), alpha=0.0)
        levelize_matrix = [
            [1, 0, 0, 0, 1],
            [0, 1, 0, 0, 1],
            [0, 0, 1, 0, 1],
            [0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0.3],
        ]
        png.color_matrix(levelize_matrix)
        png.save(filename=config.png_path + out_file + ".png")
