# Usage

To run `gerber2blend`, execute:
```
gerber2blend
```
On first use, `gerber2blend` will generate a default configuration file `blendcfg.yml` in the current directory.
This file can be adjusted to match a project, for example by changing the names of required Gerber files.

### Required input files

By default `gerber2blend` operates on fabrication outputs found in the `fab/` subdirectory in the directory from which the tool is executed.
In order to generate a model, first create a `fab/` directory:

```
cd [path to project repository]/
mkdir fab/
```

Next, you must generate the fabrication outputs using the EDA of the project.
`gerber2blend` requires the following outputs:
- Gerbers:
  - Edge Cuts
  - Front/Back Copper
  - Front/Back Silkscreen
  - Front/Back Mask
  - Front/Back Fabrication (optional)
  - Front/Back Paste (optional)
  - Inner Copper (optional)
- Drill Files (PTH/NPTH) (optional)

```{note}
The default configuration supports KiCad7 filenames for the fab files out of the box, while others will require tweaks to the `blendcfg.yaml` file.
```

### Stackup format

`gerber2blend` needs a stackup JSON file containing data about layers defined in the PCB design. An example 4-layer `stackup.json` file looks as follows:

```
{
    "layers": [
        {
            "name": "F.Silkscreen",
            "thickness": null
        },
        {
            "name": "F.Paste",
            "thickness": null
        },
        {
            "name": "F.Mask",
            "thickness": 0.01
        },
        {
            "name": "F.Cu",
            "thickness": 0.035
        },
        {
            "name": "dielectric 1",
            "thickness": 0.12
        },
        {
            "name": "In1.Cu",
            "thickness": 0.035
        },
        {
            "name": "dielectric 2",
            "thickness": 1.2
        },
        {
            "name": "In2.Cu",
            "thickness": 0.035
        },
        {
            "name": "dielectric 3",
            "thickness": 0.12
        },
        {
            "name": "B.Cu",
            "thickness": 0.035
        },
        {
            "name": "B.Mask",
            "thickness": 0.01
        },
        {
            "name": "B.Paste",
            "thickness": null
        },
        {
            "name": "B.Silkscreen",
            "thickness": null
        }
    ]
}
```

Layers named `F.Cu`, `B.Cu` or `InX.Cu` are interpreted as copper layers. `F.Mask`, `B.Mask` and `dielectric` layers are interpreted as non-copper and will be added to the prepreg mesh in the model. 

### Outputs

The resulting PCB model file, `<project-name>.blend`, is saved in `[path to project repository]/fab/`.

### Additional CLI arguments

`gerber2blend` supports the following command arguments:
* `-r` - refreshes the generated board model in `fab/<project-name>.blend` - **use it after implementing changes to input files**.
           Calling it in a project with already existing `gerber2blend` outputs will remove these files and generate new ones.
* `-c PRESET_NAME` - uses a selected `blendcfg` preset
* `-d` - enables debug logging
* `-g` - copies `blendcfg.yaml` file from template into current working directory. This will overwrite the existing config file.  
