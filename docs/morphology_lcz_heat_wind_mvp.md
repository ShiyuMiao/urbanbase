# Morphology, LCZ, and heat-wind risk MVP

## Goal

This module converts the existing VoxCity/China semantic layers into 250 m grid indicators, rule-based and prototype-distance LCZ labels, and a first-phase heat-wind compound risk table. It is designed as a CityLBM pre-screening layer, not as a calibrated CFD or heat-health model.

## Required inputs

- `outputs_citylbm_voxel_china/02_gis/aoi_boundary.gpkg`
- `outputs_citylbm_voxel_china/02_gis/fused_buildings.gpkg`
- `outputs_citylbm_voxel_china/02_gis/fused_roads.gpkg`
- `outputs_citylbm_voxel_china/02_gis/fused_green.gpkg`
- `outputs_citylbm_voxel_china/02_gis/fused_water.gpkg`
- `outputs_citylbm_voxel_china/02_gis/terrain_dem_samples.csv`
- `outputs_citylbm_voxel_china/02_gis/origin_mapping.json`

## Run order

1. `01_study_area_grid_prepare.ipynb`
2. `02_voxcity_semantic_layers_check.ipynb`
3. `03_morphology_indicator_extraction.ipynb`
4. `04_lcz_classification_uncertainty.ipynb`
5. `05_heat_wind_compound_risk.ipynb`
6. `06_visualization_typical_blocks_export.ipynb`

The same sequence can be run from the command line:

```powershell
cd "F:\0_PhD second year\第5篇：城市风环境LBM二次开发\voxcity"
python scripts\run_morphology_lcz_risk_workflow.py
```

## Main outputs

- `08_morphology/grid_250m_index.csv`
- `08_morphology/morphology_indicators_250m.csv`
- `09_lcz/lcz_classification_250m.csv`
- `14_heat_wind_risk/heat_wind_compound_risk_250m.csv`
- `15_typical_blocks/typical_blocks_for_citylbm.csv`
- `15_typical_blocks/typical_blocks_for_citylbm.geojson`
- `07_audit/morphology_lcz_risk_quality_report.json`

## Known limits

LCZ thresholds in `config/lcz_thresholds.json` are transparent first-pass rules and prototypes. They need calibration against official LCZ training samples before publication-grade classification claims. Heat-wind risk is computed from morphology proxies, blue-green ratio, terrain availability, and LCZ uncertainty; it is not a replacement for ENVI-met, WRF, CityLBM, or measured thermal comfort validation.
