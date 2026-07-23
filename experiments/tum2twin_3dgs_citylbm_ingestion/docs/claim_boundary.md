# Results Claim Boundary

## Currently Writable From This Package

- The TUM2TWIN UAS photogrammetry mesh can be downloaded, checksum-verified, and converted into Rhino-readable layered geometry and FluidX3D-compatible binary STL.
- The generated FluidX3D STL preserves the full mesh triangle count and applies a documented z0 transform for simulation-domain setup.
- The generated 3DM contains a Rhino layer inherited from the only available OBJ material group and passes programmatic readback.
- The workflow can distinguish visual textured reconstruction assets from simulation collision geometry assets.

## Not Writable Yet

- Do not claim validated urban wind prediction accuracy for TUM2TWIN; no measured wind-speed validation data or TUM2TWIN CFD results are included.
- Do not claim grid independence, LES improvement, or solver accuracy unless AIJ E1/E2/E3 and grid studies are completed and linked.
- Do not claim LoD2 vs LoD3 sensitivity conclusions; semantic CityGML LoD2/LoD3 conversion and matched CFD runs are still missing.
- Do not claim design-support effectiveness or scenario ranking; S0-S7 cases are not generated or simulated.
- Do not claim significant workflow time saving; only partial download/conversion timing exists.

## Recommended Paper Framing Now

Use this package as a reproducible data-ingestion and geometry-preparation milestone for transferring CityLBM/FluidX3D from AIJ validation to a real digital-twin scene. Treat all downstream wind maps, LoD sensitivity, and design claims as planned experiments until VTK/log/statistics artifacts exist.
