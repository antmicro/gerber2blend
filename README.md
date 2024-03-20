# gerber2blend

Copyright (c) 2022-2024 Antmicro

`gerber2blend` is a tool used for generating 3D PCB models. 
`gerber2blend` uses production data in Gerber format to generate Blender 3.2+ compatible PCB meshes in .blend format that can be used to generate realistic PCB renders. 

The tool's key features are:
* Independence of any EDA tools. `gerber2blend` relies on the [Gerber file format](https://en.wikipedia.org/wiki/Gerber_format) for mesh and material creation
* Blender 3.2+ object and material generation
* Predefined materials for common PCB types.

## Documentation

Visit the [gerber2blend documentation](https://antmicro.github.io/gerber2blend/) for more information about usage.

## Installation

### Requirements

#### Debian / Ubuntu
`gerber2blend` requires `gerbv`, `expect`, `inkscape`>=1.2.
Additionally `wget` and `xz-utils` are required for installation process (download and extraction of Blender 3.2 tar.xz).

To install it in Debian/Ubuntu run following command:
```
sudo apt install gerbv expect inkscape wget xz-utils
```

### Install

Add `~/.local/bin` to PATH:
```
export PATH=$HOME/.local/bin:$PATH
```

`gerber2blend` uses Blender 3.2 and its built-in Python3 interpreter, which are automatically installed during `gerber2blend` installation.

To install `gerber2blend`, run the following command:

```
git clone https://github.com/antmicro/gerber2blend.git
cd gerber2blend
./scripts/install.sh
```

## Getting started

To show available functionalities of `gerber2blend`, run:
```
gerber2blend --help
```

To open Blender with `gerber2blend`, run:
```
g2b_blender
```

For more information regarding `Blender`, go to the [Blender 3.2 documentation](https://docs.blender.org/manual/en/3.2/).

## License

`gerber2blend` is licensed under the Apache-2.0 license. For details, see the [LICENSE](LICENSE) file.
