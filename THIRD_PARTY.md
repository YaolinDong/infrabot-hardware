# Third-party content

## Motor models in the assembly

`assembly/infrabot-h7c_assembly.step` places the manufacturer 3D models of the joint motors at J1–J7, so the assembly shows real clearances. These models belong to Damiao. They are not covered by CERN-OHL-S-2.0, MIT or CC-BY-4.0 in this repository. Download them from Damiao for use outside this assembly.

| Joint | Motor | Model in the assembly |
|---|---|---|
| J1, J2 | DM8009P | `8009-RAU_5005` outline model |
| J3, J4 | DM-J4340P-2EC | `DM-J4340P-2EC-V1.1` model |
| J5, J6, J7 | DM-J4310-2EC | `DM-J4310-2EC-V1.1` model |

The DM-J4340P vendor model contains its own M2.5 screws and sub-assemblies. The part files under `parts/` contain no vendor geometry.

## Preview tools

`tools/render_previews.py` uses cadquery-ocp and Open CASCADE Technology (Apache-2.0 / LGPL-2.1 with the OCCT exception), VTK (BSD-3-Clause), NumPy (BSD-3-Clause) and Pillow (MIT-CMU). None of these are distributed in this repository.
