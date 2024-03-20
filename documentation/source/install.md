# Installation

## Clone the repository

Clone the repository and navigate to its contents by running:
```bash
git clone https://github.com/antmicro/gerber2blend
cd gerber2blend/
```

## Installation

Before installing, make sure that the directory `/home/[username]/.local/bin` is present in your `PATH`.
You can do this by running the following in your shell and inspecting the output:
```bash
$ echo $PATH
```
If the directory is not in the `PATH`, ensure it is added before continuing with the installation.
You can do this by extending your `.bashrc` with as follows:
```
export PATH=$HOME/.local/bin:$PATH
```

Install `gerber2blend` requirements: `gerbv`, `expect`, `inkscape>=1.2`, `wget` and `xz-utils`

### Debian/Ubuntu 

To install it in Debian/Ubuntu run following command:
```
sudo apt install gerbv expect inkscape wget xz-utils
```

----

Then run the following command from the cloned repository root to install the tool:
```bash
./scripts/install.sh
```
This installs the required dependencies, downloads a compatible Blender version and installs `gerber2blend` for use with this Blender version.

Blender is installed in the `.g2b_blender` subdirectory of the cloned repository.
Blender is currently supported in version `3.2`.

