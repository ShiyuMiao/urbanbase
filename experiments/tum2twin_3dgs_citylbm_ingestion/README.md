# TUM2TWIN 3DGS-to-CityLBM Geometry Package

This package records the completed local T1 conversion step for the TUM2TWIN UAS photogrammetry mesh and prepares templates for the later CityLBM / FluidX3D / Rhino-Grasshopper experiment chain.

## Evidence status

- `newly_run`: local checksum verification, STL export, FluidX3D z0 transform, Rhino 3DM geometry export, 3DM readback check.
- `preexisting_artifact`: TUM2TWIN / Zenodo source files and official metadata.
- `user_claim`: the planned AIJ A/E -> TUM2TWIN paper workflow and requested T1-T5 experiment design.
- `not_run`: CityLBM/FluidX3D simulation, LoD2/LoD3 semantic CityGML conversion, vegetation conversion, VTK post-processing, design intervention scenarios.

## Local model outputs

- Accurate textured Rhino source: `F:\0_PhD second year\第5篇：城市风环境LBM二次开发\实验3：3DGS模型构建\TUM2TWIN_TUM_Downtown_Photogrammetry_Mesh_20241217\raw_zenodo\TUM_Downtown_Photogrammetry_20241217_Mesh.obj` with the adjacent `.mtl` and `.jpg` files.
- Rhino 3DM layered geometry: `F:\0_PhD second year\第5篇：城市风环境LBM二次开发\实验3：3DGS模型构建\TUM2TWIN_TUM_Downtown_Photogrammetry_Mesh_20241217\converted\TUM_Downtown_Photogrammetry_20241217_rhino_layered_geometry.3dm`.
- FluidX3D / CityLBM STL: `F:\0_PhD second year\第5篇：城市风环境LBM二次开发\实验3：3DGS模型构建\TUM2TWIN_TUM_Downtown_Photogrammetry_Mesh_20241217\converted\TUM_Downtown_Photogrammetry_20241217_fluidx3d_z0_fullres.stl`.
- Visual local-coordinate STL: `F:\0_PhD second year\第5篇：城市风环境LBM二次开发\实验3：3DGS模型构建\TUM2TWIN_TUM_Downtown_Photogrammetry_Mesh_20241217\converted\TUM_Downtown_Photogrammetry_20241217_visual_local_fullres.stl`.

## Rhino layer and texture boundary

The source OBJ has one material group: `material`. It does not contain multiple Rhino layers. The generated 3DM therefore contains one inherited/provenance layer:

`TUM2TWIN::UAS_Photogrammetry_Mesh::material`

The 3DM stores the full mesh geometry, layer, material name, texture file reference, and provenance user strings. However, the Python `rhino3dm` API used here cannot write the OBJ `vt` texture atlas into the 3DM. For accurate textured visualization, open/import the OBJ directly in Rhino; keep the MTL and JPG in the same folder.

## FluidX3D / CityLBM boundary

The STL export is geometry-only by design. The `fluidx3d_z0` STL applies:

`z_fluidx3d = z_local + 49.265300`

This sets the lowest mesh point to `z=0`. It is suitable as a first geometry ingestion test, but the photogrammetry mesh is not a clean watertight building-solid ground truth. For publication-grade CFD collision solids and IoU/distance validation, use the TUM2TWIN CityGML LoD2/LoD3 semantic building models.

## Official sources

- TUM2TWIN UAS mesh page: https://tum2t.win/datasets/cm-mesh
- Zenodo record: https://zenodo.org/records/15282970
- Zenodo DOI: https://doi.org/10.5281/zenodo.15282970
- TUM2TWIN facade benchmark page read for context: https://tum2t.win/benchmarks/pc-fac
- TUM2TWIN semantic building models: https://tum2t.win/datasets/cm-buildings
- TUM2TWIN CAD models: https://tum2t.win/datasets/cm-cad

## Package contents

- `manifests/`: source, output, checksum, STL conversion, and 3DM readback manifests.
- `results/`: current evidence inventory, missing artifact list, T1 actual QA row, and workflow log.
- `templates/`: CSV and JSON metadata templates for modules T1-T5.
- `docs/`: execution checklist and claim boundary for the SCI paper Results section.
- `scripts/`: reproducible conversion and verification scripts.
