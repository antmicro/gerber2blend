# Processing pipeline

`gerber2blend` operates on preconfigured pipelines.
These pipelines are defined in the `blendcfg.yaml` configuration file.
The following board generation pipeline is created by default:
```yaml
  STAGES:
    - CLEARSCENE:
    - GERBCONVERT:
    - BOARD:
    - VERSIONSTAMPER:
```

Each stage in the pipeline is provided from the `modules` package in the Blender Python environment.
For example, `GERBCONVERT` is defined in the [modules/gerbv_convert.py](../../src/modules/gerbv_convert.py) file:
```python
import os
import sys
import shutil

# ...

class GerbConvert(core.module.Module):
    """ Module to convert Gerbers to the required intermediate files
    """
    def execute(self):
        """ Run the module
        """
        fio.rename_gerbers_if_new_names(config.path)
        fio.check_gbr_csv_files_exist(config.path, config.g2b_dir_path)
        # ...
```
A single Python file can contain multiple stage definitions.
A stage **must** inherit from the `core.module.Module` base class to be discoverable by `gerber2blend`.
To call a stage from `blendcfg.yaml`, refer to the stage's class name in **uppercase** (`GERBCONVERT`, in this case) for `gerber2blend` to dynamically load and run the code defined in the `execute` method for the class.
The `execute` method for a stage is called when all previous stages are completed successfully.

## Available stages

- `GERBCONVERT` - performs conversion of input Gerber files to SVG/PNG. The input files are taken from the `GERBER_FILENAMES` configuration section, and the output is stored in the `fab/PNG` and `fab/SVG` directories.
- `BOARD` - generates a PCB model from `fab/SVG` and `fab/PNG` input files.
- `VERSIONSTAMPER` - saves Git commit metadata in the created model (`gerber2blend` and PCB design repository revision)