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

Install `gerber2blend` requirements: `gerbv`, `python3.11`, `inkscape>=1.2`

### Debian/Ubuntu 

To install it in Debian/Ubuntu run following command:
```
sudo apt install gerbv inkscape python3.11 python3.11-venv
```

----

Then run the following command from the cloned repository root to install the tool:
```bash
python3.11 -m venv venv
source /venv/bin/activate
pip install .
```
This installs the required dependencies and installs `gerber2blend` compatibile with Blender.
Blender is currently supported in version `4.1`.
