# Installation

## Install dependencies

To install it in Debian/Ubuntu run following command:

```bash
sudo apt-get update
sudo apt install gerbv inkscape python3.11 python3.11-venv pipx
```

```{note}
`gerbv 2.10` installation is recommended as earlier versions may result in broken Gerber exports.
```

## Configure PATH

Before installing, make sure that the directory `/home/[username]/.local/bin` is present in your `PATH`.
You can do this by running the following in your shell and inspecting the output:

```bash
export PATH=$HOME/.local/bin:$PATH
```

## Clone and install `gerber2blend`

Clone the repository, navigate to its contents and install by running:

```bash
python3.11 -m pipx install 'git+https://github.com/antmicro/gerber2blend.git'
```

```{note}
Installation for developers:

    git clone https://github.com/antmicro/gerber2blend.git
    python3.11 -m pipx install --editable .

```

This installs the required dependencies and installs `gerber2blend` compatibile with Blender.
Blender is currently supported in version `4.1`.
