# Street-view facade carving Phase 1

## Scope

This phase adds the legal and reproducible base layer for street-view driven facade refinement. It does not download restricted street-view imagery and does not fabricate facade details. Images must be self-captured, manually supplied, or obtained from licensed providers such as Mapillary or KartaView outside this runner.

## Current outputs

- `templates/streetview_metadata_template.csv`: required metadata schema for authorized images.
- `src/streetview_facade/metadata.py`: metadata parsing, provider allow-list, license/image existence audit.
- `src/streetview_facade/coordinates.py`: WGS84 to local tangent-plane conversion and camera/facade geometry helpers.
- `src/streetview_facade/facade.py`: building footprint edge extraction into facade planes.
- `src/streetview_facade/manual_pipeline.py`: Phase 1 runner that writes `metadata_audit.csv`, `facade_planes.csv`, `image_facade_matches.csv`, and `summary.json`.
- `notebooks/streetview_facade_phase1_manual_import.ipynb`: notebook entry for manual experiments.
- `scripts/validate_streetview_phase1.py`: small deterministic validation on a synthetic square footprint and a local placeholder image.

## How to run

```powershell
cd "F:\0_PhD second year\第5篇：城市风环境LBM二次开发\voxcity"
python -m scripts.validate_streetview_phase1
```

For a real site, copy the template, replace every row with real authorized images, and point `building_path` to a real building footprint layer from the existing VoxCity/China pipeline, for example `outputs_citylbm_voxel_china/02_gis/fused_buildings.gpkg`.

## Data contract

The metadata CSV requires `image_id`, `image_path`, `lon`, `lat`, and `provider`. Coordinates must be WGS84 `EPSG:4326`. Optional fields include heading, pitch, roll, horizontal field of view, camera height, license, photographer, target building id, and notes.

Allowed provider labels are `manual`, `self_capture`, `mapillary`, and `kartaview`. Provider labels document provenance only; this module never calls provider APIs.

## Next implementation steps

1. Add manual point correspondence schema for image pixels to facade-local coordinates.
2. Add GroundingDINO/SAM2 segmentation adapters behind optional dependency gates.
3. Add Depth Anything V2 depth-map import and metric-scale alignment using facade/control points.
4. Project semantic/depth evidence to facade planes and output facade-local feature polygons.
5. Convert facade features to voxel carving constraints and merge with `china_voxel_pipeline.py` sparse voxel tables.
