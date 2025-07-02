# Blender Animated Voxelizer

A Blender addon that converts 3D objects into voxel-style cube meshes — frame-by-frame — with support for assigning custom materials and exporting animated voxel sequences.

[# blender-animated-voxelizer](https://github.com/user-attachments/assets/7d621e29-a296-47b1-a9bf-e7bc0e0c075a)

## Features

- Voxelizes a target object with customizable resolution
- Supports multiple animation frames (frame range or list)
- Assigns any Blender material to the voxel mesh
- Single `.py` script, no external dependencies

## Requirements

- **Blender 4.2.4 LTS** (or later)

## Usage

1. Download `voxel_addon.py` from this repository
2. Open Blender, go to **Edit → Preferences → Add-ons → Install**
3. Select `voxel_addon.py` and enable it
4. In the 3D Viewport, open the **Sidebar (N)** → **Voxel** tab
5. Select your target object and set the desired parameters

### Notes

- The **Frames** field lets you specify exact animation frames (e.g., `1,10,20`). A voxel mesh will be generated for each frame in the list.
- A material dropdown allows you to assign an existing Blender material to all generated voxels.

## Live Playground

You can see an example of the exported voxelized mesh used in Babylon.js here:

👉 [Babylon.js Playground Example](https://playground.babylonjs.com/#ZOF2YX#1)

This demo loads a glTF file exported from Blender using this addon, and renders it in a WebGL environment.

## License

MIT License
