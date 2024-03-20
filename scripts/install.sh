#!/usr/bin/env bash
set -e

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
REPO_DIR="$SCRIPT_DIR/../"
IN_CI=''
TOOLNAME="gerber2blend"
USERBIN="${HOME}/.local/bin"
# Blender installation config
BLENDER_TAR="https://mirrors.dotsrc.org/blender/release/Blender3.2/blender-3.2.2-linux-x64.tar.xz"
BLENDER_TAR_SHA256="1726560157d90cf2aaaeb6d25ded1783d66bff043814cd95b90fc0af1d9e018b"
# Name of the downloaded archive file
BLENDER_TAR_TMP_FILE="g2b_blender.tar.xz"
BLENDER_INSTALL_DIR="${REPO_DIR}/.g2b_blender"
SUDO=""
if [ "${UID}" != "0" ]; then
    SUDO="sudo"
fi
# Allow overriding the used version for CI jobs
if [ -n "${G2B_BLENDER_TAR_URL}" ]; then
    BLENDER_TAR="${G2B_BLENDER_TAR_URL}"
fi
if [ -n "${G2B_BLENDER_TAR_SHA256}" ]; then
    BLENDER_TAR_SHA256="${G2B_BLENDER_TAR_SHA256}"
fi

path_check()
{
    # Check both ${USERBIN} and ${USERBIN}/ variants
    if [[ ":$PATH:" != *":${USERBIN}:"* ]] && [[ ":$PATH:" != *":${USERBIN}/:"* ]]; then
        cat <<EOF


WARNING: You do not have the directory ${USERBIN} present in your \$PATH.
To ensure ${TOOLNAME} is runnable, add the directory to your \$PATH variable (for example
by adding it in ~/.bashrc when using Bash).


EOF
    fi
}

parse_args()
{
    while getopts c name
    do
        case $name in
        c) IN_CI='-y';;
        ?) echo "Usage: $0: [-c]"
            exit 2;;
        esac
    done
}

install_blender()
{
    if [ ! -f "${BLENDER_TAR_TMP_FILE}" ]; then
        echo "Downloading Blender from ${BLENDER_TAR} to ${BLENDER_TAR_TMP_FILE}"
        wget -cnv "${BLENDER_TAR}" -O "${BLENDER_TAR_TMP_FILE}"
    else
        echo "${BLENDER_TAR_TMP_FILE} already exists, skipping download"
    fi

    echo "Verifying SHA256 of ${BLENDER_TAR_TMP_FILE}.."
    if ! echo "${BLENDER_TAR_SHA256}  ${BLENDER_TAR_TMP_FILE}" | sha256sum --check 2>&1 ; then
        ACTUAL_HASH=$(sha256sum "${BLENDER_TAR_TMP_FILE}" | head -c 64)

        cat 2>&1 <<EOF

ERROR: Checksum verification of archive ${BLENDER_TAR_TMP_FILE} failed!
Either the upstream archive changed, or you forgot to update the hash
after changing versions!

Archive downloaded from: ${BLENDER_TAR}
Expected SHA256: ${BLENDER_TAR_SHA256}
Actual SHA256: ${ACTUAL_HASH}

EOF
        return 1
    fi

    echo "Extracting Blender archive.."
    mkdir -p "${BLENDER_INSTALL_DIR}"
    tar -xJf "${BLENDER_TAR_TMP_FILE}" --directory="${BLENDER_INSTALL_DIR}" --strip-components 1

    echo "Creating symlinks.."
    mkdir --parents "${USERBIN}"
    ln -sf "${BLENDER_INSTALL_DIR}/blender" "${USERBIN}/g2b_blender"
    echo "Installed g2b_blender"
}


check_for_blender()
{
    echo "Checking for a supported Blender installation.."
    if ! command -v g2b_blender >/dev/null 2>&1 ; then
        echo "Could not find g2b_blender; attempting to install it.."
        install_blender
    fi

    BLENDER_DIR=$(dirname $(readlink -f $(which g2b_blender)))
    PYTHON="$BLENDER_DIR/*/python/bin/python3.10"

    echo "NOTE: Using Blender from: ${BLENDER_DIR}"
    echo "NOTE: Blender Python interpreter: ${PYTHON}"
}


install_in_blender()
{
    echo "Installing ${TOOLNAME} inside the Blender Python environment.."
    $PYTHON -m ensurepip
    $PYTHON -m pip install --upgrade pip
    $PYTHON -m pip install "${REPO_DIR}"
}

apply_workarounds()
{
    # Remove problematic line from glTF module, see #48344
    sed  -i 's/bpy.types.NODE_MT_category_SH_NEW_OUTPUT.append(add_gltf_settings_to_menu)/#bpy.types.NODE_MT_category_SH_NEW_OUTPUT.append(add_gltf_settings_to_menu)/' "$BLENDER_DIR/3.2/scripts/addons/io_scene_gltf2/blender/com/gltf2_blender_ui.py"
}

create_links()
{
    _toolpath="${USERBIN}/${TOOLNAME}"

    echo "Installing ${TOOLNAME} runner script in ${USERBIN}.."
    mkdir --verbose --parents ${USERBIN}
    ln -sf "${REPO_DIR}/scripts/generate.sh" "${_toolpath}"

    echo "${TOOLNAME} was installed in ${_toolpath}!"
}


echo "---------------------------------"
echo "Installing ${TOOLNAME}"
echo "---------------------------------"

parse_args
path_check
check_for_blender
install_in_blender
apply_workarounds
create_links

echo "DONE"
echo "---------------------------------"
