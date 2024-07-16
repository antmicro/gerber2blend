# gerber2blend

Copyright (c) 2022-2024 Antmicro

![](img/gerber2blend-vis.png)

`gerber2blend` is an open-source utility dedicated to generating 3D models of Printed Circuit Boards (PCBs) in Blender (.blend) format.
The tool uses Gerber (Gerber RS-274X) input files that are used for producing physical PCBs.
This makes the PCB visualization independent from the software used for designing it.
Currently `gerber2blend` supports Blender 4.1+.

## Installation

### Requirements

`gerber2blend` depends on the following packages:

* gerbv (recommended >=2.10)
* inkscape >= 1.2
* python3.11, pipx

Additionally to preview and modify the generated .blend file [Blender 4.1](https://www.blender.org/download/releases/4-1/) needs to be installed.

### Installation (Debian)

1. Install the dependencies:

    ```bash
    sudo apt-get update
    sudo apt install gerbv inkscape python3.11 python3.11-venv pipx
    ```

2. Configure PATH:

    ```bash
    export PATH=$HOME/.local/bin:$PATH
    ```

3. Clone and install `gerber2blend`:

    ```bash
    python3.11 -m pipx install 'git+https://github.com/antmicro/gerber2blend.git'
    ```

## Usage

Please check the [gerber2blend documentation](https://antmicro.github.io/gerber2blend/) for more guidelines.

To show available functionalities of `gerber2blend`, run:

```bash
gerber2blend --help
```

For more information regarding Blender supported by the `gerber2blend` visit the [Blender 4.1 documentation](https://docs.blender.org/manual/en/4.1/).

## License

The `gerber2blend` utility is licensed under the Apache-2.0 [license](LICENSE).
