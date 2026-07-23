# TUM2TWIN Experiment Execution Checklist

## T1 Geometry Conversion and QA

- [x] Record source, version, download route, and license for the UAS photogrammetry mesh.
- [x] Verify downloaded OBJ/MTL/JPG/offset checksums against Zenodo.
- [x] Export full-resolution binary STL in source local coordinates.
- [x] Export full-resolution binary STL with minimum z shifted to 0 for FluidX3D/CityLBM setup.
- [x] Export Rhino-readable 3DM layered geometry.
- [x] Verify 3DM readback: layer exists, object exists, mesh counts match.
- [ ] Convert CityGML LoD2 semantic building solids for the selected 250-300 m subarea.
- [ ] Convert CityGML LoD3 semantic building solids for the selected 250-300 m subarea.
- [ ] Convert vegetation/tree models if G4 is used.
- [ ] Generate Grasshopper SceneData/domain/grid/voxel mask.
- [ ] Run watertightness, footprint, height, volume, and voxelization QA.

## T2 Baseline Wind Environment

- [ ] Define common domain, boundary conditions, Uref, reference height, and inflow profile.
- [ ] Generate 8 wind-direction CityLBM / FluidX3D cases.
- [ ] Run simulations and save VTK/log/metadata.
- [ ] Extract pedestrian-height wind speed ratio maps and statistics.

## T3 LoD Sensitivity

- [ ] Prepare G1 LoD2, G2 LoD3, G3 simplified LoD3, and optional G4 vegetation geometry.
- [ ] Run selected critical wind directions under identical solver settings.
- [ ] Compute hotspot/coldspot/comfort IoU and ranking stability.

## T4 Design Intervention

- [ ] Create S0-S7 Rhino-Grasshopper scenario geometries.
- [ ] Run identical wind/settings cases for selected directions.
- [ ] Compute improvement metrics and scenario ranking.

## T5 Workflow Efficiency and Reproducibility

- [ ] Record full download-to-figure timing and manual/automatic step counts.
- [ ] Record failures, reruns, and manual repairs.
- [ ] Package scripts, model references, VTK paths, figures, CSV, JSON, and claim boundary.
