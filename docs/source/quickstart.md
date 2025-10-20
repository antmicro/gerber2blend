# Quick start

3D model of the Open Source [Jetson Orin Baseboard](https://github.com/antmicro/jetson-orin-baseboard) will be generated as example.

## Clone the board

```
git clone https://github.com/antmicro/jetson-orin-baseboard.git
```

## Gerber generation

### Install KiCad

Open Source EDA tool [KiCad](https://www.kicad.org/) will be used for generation of the `Gerber` format files for the board.
KiCad from version 7.0.0 provides CLI that can be used in the command line and CI environment.
To install KiCad run:
```
sudo apt install kicad
```


### Gerbers generation

To generate gerber files run:
```
cd jetson-orin-baseboard  
mkdir fab
kicad-cli pcb export gerbers --no-protel-ext -o fab/ jetson-orin-baseboard.kicad_pcb
kicad-cli pcb export drill --format gerber --excellon-separate-th -o fab/ jetson-orin-baseboard.kicad_pcb
```

Tool like [KiCad builtin Gerber Viewer](https://www.kicad.org/discover/gerber-viewer/) or [Gerbv](https://gerbv.github.io/) can be used to preview the gerbers.

For example, to open gerbers for preview with `Gerber Viewer` run:
```
gerbview fab/*
```

### Generate PCB model using `gerber2blend`

To generate a 3D model of the board, run:
```
cd jetson-orin-baseboard
gerber2blend
```

`.blend` file will be created in the `fab` directory.

To preview generated `.blend` file, open it with instance of Blender in version >=4.4.

