# GitHub Release Manifest

Updated: 2026-07-21

This manifest defines the files that should be staged for the `voxcity-open-streetview-facade-dut-library` GitHub source release. The release package is intentionally whitelist-based so legacy cache files, temporary run folders, and large geospatial/model assets are not mixed into normal Git history.

## 1. Normal Git Source Files

Core project files:

```text
.gitignore
README.md
requirements.txt
GITHUB_RELEASE_MANIFEST.md
SOFTWARE_OPTIMIZATION_PLAN_VOXEL_CARVING.md
CURRENT_PROGRESS_ZHONGSHAN_RELEASE_REPORT.md
CityLBM_VoxCity_China_0p1m_RhinoVoxel_full_process.ipynb
voxcity_demo (4).py
```

Source packages:

```text
src/**/*.py
```

Command-line runners, QA tools, and smoke/stability tests:

```text
scripts/*.py
```

Configuration, documentation, notebooks, and templates:

```text
config/**/*.json
docs/**/*.md
notebooks/**/*.ipynb
templates/**/*
```

This includes the current minimum usable pipeline:

```text
scripts/run_site_model.py
scripts/qa_site_output.py
scripts/audit_git_release_status.py
scripts/test_git_release_status_audit.py
scripts/run_stability_checks.py
scripts/test_release_staging_integrity.py
scripts/test_cross_china_coordinate_preflight.py
scripts/test_cross_china_e2e_probe.py
scripts/test_worldcover_selection.py
scripts/audit_worldcover_coverage.py
scripts/plan_worldcover_tiles.py
scripts/test_worldcover_tile_manifest.py
scripts/validate_worldcover_tiles.py
scripts/test_worldcover_tile_validation.py
scripts/validate_osm_cache.py
scripts/test_osm_cache_validation.py
scripts/validate_dem_cache.py
scripts/test_dem_cache_validation.py
scripts/real_data_readiness_report.py
scripts/test_real_data_readiness_report.py
scripts/preflight_site_data_sources.py
scripts/test_site_data_preflight.py
scripts/prepare_site_data_sources.py
scripts/test_prepare_site_data_sources.py
scripts/test_site_model_runner_and_qa.py
scripts/test_morphology_lcz_risk_workflow.py
scripts/test_sequential_notebooks.py
scripts/test_tiny_site_e2e.py
scripts/test_multi_site_e2e.py
scripts/test_release_staging_integrity.py
src/china_voxel_pipeline.py
src/urban_morphology/
config/lcz_thresholds.json
notebooks/01_study_area_grid_prepare.ipynb
notebooks/02_voxcity_semantic_layers_check.ipynb
notebooks/03_morphology_indicator_extraction.ipynb
notebooks/04_lcz_classification_uncertainty.ipynb
notebooks/05_heat_wind_compound_risk.ipynb
notebooks/06_visualization_typical_blocks_export.ipynb
```

The release integrity test must also verify staged copies of the morphology,
LCZ, heat-wind risk, typical-block, and QA modules. In particular,
`scripts/qa_site_output.py` now checks both table schemas and numeric value
ranges so invalid ratios, probabilities, risk scores, non-finite values, or
terrain ordering errors are caught before publishing.

## 2. Small DUT Library Example Output Files

The default release staging script includes small, reviewable files from the DUT west-campus library reference example:

```text
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/basic_site_statistics.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/basic_site_statistics.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/layer_summary_statistics.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/layer_element_statistics.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/scene_classification_alcc_lcz.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/scene_classification_metrics.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/scene_morphology_lcz_formula_notes.md
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/vegetation_layer_quality_summary.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/esa_worldcover_landcover_metadata.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/05_rhino/final_city_voxel_1m_metadata.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/05_rhino/final_city_voxel_1m_layers.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/05_rhino/final_city_voxel_1m_object_mapping.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/08_morphology/grid_250m_index.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/08_morphology/grid_prepare_summary.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/08_morphology/morphology_indicator_schema.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/08_morphology/morphology_indicators_250m.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/09_lcz/lcz_classification_250m.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/09_lcz/lcz_classification_summary.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/14_heat_wind_risk/heat_wind_compound_risk_250m.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/14_heat_wind_risk/heat_wind_compound_risk_summary.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/15_typical_blocks/typical_blocks_for_citylbm.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/15_typical_blocks/typical_blocks_summary.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/07_audit/real_data_source_check.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/07_audit/data_quality_audit.csv
outputs_citylbm_voxel_china/dalian_dlut_west_library/07_audit/data_quality_audit.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/10_figures/dalian_dlut_west_library_voxel_model_review.png
10_figures_tables/versioned_screenshots/2026-07-21_v0.2.0_dut_library_1m_rhino_groups_lcz_street_trees.png
10_figures_tables/versioned_screenshots/2026-07-13_v6_dut_library_all_element_voxel_model.png
10_figures_tables/versioned_screenshots/2026-07-09_v1_manual_multiview_facade_result.png
outputs_citylbm_voxel_china/dalian_dlut_west_library/12_logs/final_execution_report.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/12_logs/site_output_qa.json
outputs_citylbm_voxel_china/dalian_dlut_west_library/12_logs/site_model_summary.json
```

## 3. Large Assets

These files are reproducible model/data artifacts, but should not be committed directly to normal Git history. Use Git LFS or GitHub Release assets:

```text
outputs_citylbm_voxel_china/dalian_dlut_west_library/05_rhino/final_city_voxel_1m.3dm
outputs_citylbm_voxel_china/dalian_dlut_west_library/05_rhino/final_city_voxel_1m_v0p2p0.3dm
outputs_citylbm_voxel_china/dalian_dlut_west_library/04_voxels/sparse_voxels.csv
outputs_citylbm_voxel_china/01_raw/ESA_WorldCover_10m_2021_v200_N36E120_Map.tif
```

For v0.2.0, `final_city_voxel_1m_metadata.json` records the actual Rhino file
used for QA. If the canonical `final_city_voxel_1m.3dm` is open in Rhino and
cannot be overwritten on Windows, the exporter writes a versioned file such as
`final_city_voxel_1m_v0p2p0.3dm`; the release staging script reads that metadata
before copying large assets.

## 4. Legacy And Temporary Outputs

Do not mix root-level legacy outputs or temporary smoke-test folders into a normal source commit:

```text
outputs_citylbm_voxel_china/02_gis/
outputs_citylbm_voxel_china/04_voxels/
outputs_citylbm_voxel_china/05_rhino/
outputs_citylbm_voxel_china/06_tables/
outputs_citylbm_voxel_china/07_audit/
outputs_citylbm_voxel_china/08_morphology/
outputs_citylbm_voxel_china/09_lcz/
outputs_citylbm_voxel_china/10_figures/
outputs_citylbm_voxel_china/11_docs/
outputs_citylbm_voxel_china/12_logs/
outputs_citylbm_voxel_china/14_heat_wind_risk/
outputs_citylbm_voxel_china/15_typical_blocks/
outputs_citylbm_voxel_china/_smoke_*/
outputs_citylbm_voxel_china/_probe_*/
outputs_citylbm_voxel_china/_full_e2e_*/
outputs_citylbm_voxel_china/01_raw/legacy_*
```

Some legacy root output files are already tracked by Git. Do not use broad cleanup commands or `git reset --hard`; decide separately whether those files should remain as a historical snapshot, be moved to release assets, or be replaced in a dedicated cleanup commit.

## 5. Release Staging Command

Use a new empty target folder for each staging run:

```powershell
python scripts\prepare_github_release.py --target _release\voxcity-open-streetview-facade-dut-library_source_YYYYMMDD_HHMMSS
```

Use `--include-large-assets` only when preparing a local archive or a GitHub Release asset bundle:

```powershell
python scripts\prepare_github_release.py --target _release\voxcity-open-streetview-facade-dut-library_with_assets_YYYYMMDD_HHMMSS --include-large-assets
```

## 6. Minimum Verification

Run these commands before publishing:

```powershell
git status --short
python scripts\audit_git_release_status.py
python scripts\audit_git_release_status.py --cleanup-plan-json _release\tracked_output_cleanup_plan.json
python -m py_compile src\china_voxel_pipeline.py scripts\run_site_model.py scripts\qa_site_output.py scripts\audit_git_release_status.py scripts\run_stability_checks.py scripts\prepare_github_release.py
python scripts\audit_worldcover_coverage.py
python scripts\plan_worldcover_tiles.py  # writes WorldCover JSON/CSV plus GEE export JS for missing real-data tiles
python scripts\validate_worldcover_tiles.py  # validates downloaded WorldCover GeoTIFFs before strict real-data runs
python scripts\validate_osm_cache.py --site-name dalian_dlut_west_library --site-name-cn dalian_dlut_west_library --lat 38.8831553 --lon 121.5120457 --voxel-size-m 1.0 --strict
python scripts\validate_dem_cache.py --site-name dalian_dlut_west_library --site-name-cn dalian_dlut_west_library --lat 38.8831553 --lon 121.5120457 --voxel-size-m 1.0 --strict
python scripts\real_data_readiness_report.py --site-name dalian_dlut_west_library --site-name-cn dalian_dlut_west_library --lat 38.8831553 --lon 121.5120457 --voxel-size-m 1.0 --strict
python scripts\preflight_site_data_sources.py --site-name dalian_dlut_west_library --site-name-cn dalian_dlut_west_library --lat 38.8831553 --lon 121.5120457 --voxel-size-m 1.0 --strict
python scripts\prepare_site_data_sources.py --site-name dalian_dlut_west_library --site-name-cn dalian_dlut_west_library --lat 38.8831553 --lon 121.5120457 --voxel-size-m 1.0 --strict
python scripts\test_release_staging_integrity.py
python scripts\run_stability_checks.py --timeout-s 900 --strict-worldcover-coverage --include-tiny-e2e --include-multi-site-e2e --include-cross-china-e2e --strict-cross-china-real-data
python scripts\qa_site_output.py --output-root outputs_citylbm_voxel_china\dalian_dlut_west_library --min-buildings 1 --min-green-features 1 --min-dem-relief-m 1.0 --expected-lat 38.8831553 --expected-lon 121.5120457 --expected-aoi-width-m 500 --expected-voxel-size-m 1.0 --require-layer-token Buildings_ --require-layer-token Roads_Hardscape_ --require-layer-token Green_Trees_ --require-layer-token Green_Grass_ --require-layer-token Terrain_DEM_ --require-real-data-sources
```

Optional local staging check:

```powershell
python scripts\prepare_github_release.py --target _release\voxcity-open-streetview-facade-dut-library_check_YYYYMMDD_HHMMSS
```
