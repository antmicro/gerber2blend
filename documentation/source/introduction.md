# Introduction

`gerber2blend` is a tool created to automate PCB 3D model generation and post-processing of the generated models.
The tool utilizes fabrication files in Gerber format to create a Blender model of PCBs.
Models are processed by a module pipeline, with each module performing a certain processing step, all configurable using a YAML file.

* [Getting started](usage.md) describes the installation process and presents a basic usage example.
* [Configuring blendcfg.yaml](blendcfg.md) presents configuration options available for customizing the processing workflow.
* [Processing pipeline](pipeline.md) describes operation principles of the pipeline mechanism.
