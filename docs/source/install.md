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
### glTF support

`gerber2blend` supports exporting PCB model to glTF format. To use that functionality you need [KTX-Software](https://github.com/KhronosGroup/KTX-Software/tree/main) and `gltf-transform` `npm` package installed:

    ```bash
    wget https://github.com/KhronosGroup/KTX-Software/releases/download/v4.4.0/KTX-Software-4.4.0-Linux-x86_64.deb
    sudo dpkg --install KTX-Software-4.4.0-Linux-x86_64.deb
    sudo apt install npm
    nvm use 22
    npm install -g @gltf-transform/cli@4.2.0 @gltf-transform/core@4.2.0 @gltf-transform/extensions@4.2.0 @gltf-transform/functions@4.2.0
    ```

```{warning}
`gltf-transform` requires Node version >= 22.
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
    cd gerber2blend
    python3.11 -m pipx install --editable .

```

This installs the required dependencies and installs `gerber2blend` compatibile with Blender.
Blender is currently supported in version `4.4`.
