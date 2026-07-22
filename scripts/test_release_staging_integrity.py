from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from prepare_github_release import prepare


REQUIRED_STAGE_FILES = [
    "README.md",
    "GITHUB_RELEASE_MANIFEST.md",
    "requirements.txt",
    "src/china_voxel_pipeline.py",
    "src/urban_morphology/__init__.py",
    "src/urban_morphology/coordinates.py",
    "src/urban_morphology/grid.py",
    "src/urban_morphology/indicators.py",
    "src/urban_morphology/lcz.py",
    "src/urban_morphology/paths.py",
    "src/urban_morphology/quality.py",
    "src/urban_morphology/risk.py",
    "src/urban_morphology/typical_blocks.py",
    "src/urban_morphology/visualization.py",
    "src/urban_morphology/workflow.py",
    "config/lcz_thresholds.json",
    "docs/morphology_lcz_heat_wind_mvp.md",
    "templates/streetview_metadata_template.csv",
    "scripts/run_site_model.py",
    "scripts/run_morphology_lcz_risk_workflow.py",
    "scripts/audit_git_release_status.py",
    "scripts/test_git_release_status_audit.py",
    "scripts/qa_site_output.py",
    "scripts/run_stability_checks.py",
    "scripts/test_cross_china_coordinate_preflight.py",
    "scripts/test_cross_china_e2e_probe.py",
    "scripts/test_worldcover_selection.py",
    "scripts/audit_worldcover_coverage.py",
    "scripts/plan_worldcover_tiles.py",
    "scripts/test_worldcover_tile_manifest.py",
    "scripts/validate_worldcover_tiles.py",
    "scripts/test_worldcover_tile_validation.py",
    "scripts/test_stability_worldcover_gate.py",
    "scripts/validate_osm_cache.py",
    "scripts/test_osm_cache_validation.py",
    "scripts/validate_dem_cache.py",
    "scripts/test_dem_cache_validation.py",
    "scripts/real_data_readiness_report.py",
    "scripts/test_real_data_readiness_report.py",
    "scripts/preflight_site_data_sources.py",
    "scripts/test_site_data_preflight.py",
    "scripts/prepare_site_data_sources.py",
    "scripts/test_prepare_site_data_sources.py",
    "scripts/test_site_model_runner_and_qa.py",
    "scripts/test_morphology_lcz_risk_workflow.py",
    "scripts/test_sequential_notebooks.py",
    "scripts/test_tiny_site_e2e.py",
    "scripts/test_multi_site_e2e.py",
    "scripts/test_release_staging_integrity.py",
    "notebooks/01_study_area_grid_prepare.ipynb",
    "notebooks/02_voxcity_semantic_layers_check.ipynb",
    "notebooks/03_morphology_indicator_extraction.ipynb",
    "notebooks/04_lcz_classification_uncertainty.ipynb",
    "notebooks/05_heat_wind_compound_risk.ipynb",
    "notebooks/06_visualization_typical_blocks_export.ipynb",
    "outputs_citylbm_voxel_china/dalian_dlut_west_library/06_tables/basic_site_statistics.json",
    "outputs_citylbm_voxel_china/dalian_dlut_west_library/08_morphology/morphology_indicators_250m.csv",
    "outputs_citylbm_voxel_china/dalian_dlut_west_library/09_lcz/lcz_classification_250m.csv",
    "outputs_citylbm_voxel_china/dalian_dlut_west_library/14_heat_wind_risk/heat_wind_compound_risk_250m.csv",
    "outputs_citylbm_voxel_china/dalian_dlut_west_library/15_typical_blocks/typical_blocks_for_citylbm.csv",
    "outputs_citylbm_voxel_china/dalian_dlut_west_library/10_figures/dalian_dlut_west_library_voxel_model_review.png",
    "10_figures_tables/versioned_screenshots/2026-07-21_v0.2.0_dut_library_1m_rhino_groups_lcz_street_trees.png",
    "10_figures_tables/versioned_screenshots/2026-07-13_v6_dut_library_all_element_voxel_model.png",
    "10_figures_tables/versioned_screenshots/2026-07-09_v1_manual_multiview_facade_result.png",
]

STAGED_COMPILE_FILES = [
    "src/china_voxel_pipeline.py",
    "scripts/run_site_model.py",
    "scripts/audit_git_release_status.py",
    "scripts/test_git_release_status_audit.py",
    "scripts/qa_site_output.py",
    "scripts/test_site_model_runner_and_qa.py",
    "scripts/test_cross_china_coordinate_preflight.py",
    "scripts/test_cross_china_e2e_probe.py",
    "scripts/test_worldcover_selection.py",
    "scripts/run_stability_checks.py",
    "scripts/audit_worldcover_coverage.py",
    "scripts/plan_worldcover_tiles.py",
    "scripts/test_worldcover_tile_manifest.py",
    "scripts/validate_worldcover_tiles.py",
    "scripts/test_worldcover_tile_validation.py",
    "scripts/test_stability_worldcover_gate.py",
    "scripts/validate_osm_cache.py",
    "scripts/test_osm_cache_validation.py",
    "scripts/validate_dem_cache.py",
    "scripts/test_dem_cache_validation.py",
    "scripts/real_data_readiness_report.py",
    "scripts/test_real_data_readiness_report.py",
    "scripts/preflight_site_data_sources.py",
    "scripts/test_site_data_preflight.py",
    "scripts/prepare_site_data_sources.py",
    "scripts/test_prepare_site_data_sources.py",
    "scripts/test_release_staging_integrity.py",
    "scripts/test_morphology_lcz_risk_workflow.py",
    "scripts/test_sequential_notebooks.py",
    "scripts/test_tiny_site_e2e.py",
    "scripts/test_multi_site_e2e.py",
    "scripts/backfill_site_model_summary.py",
    "scripts/prepare_github_release.py",
    "src/urban_morphology/__init__.py",
    "src/urban_morphology/coordinates.py",
    "src/urban_morphology/grid.py",
    "src/urban_morphology/indicators.py",
    "src/urban_morphology/lcz.py",
    "src/urban_morphology/paths.py",
    "src/urban_morphology/quality.py",
    "src/urban_morphology/risk.py",
    "src/urban_morphology/typical_blocks.py",
    "src/urban_morphology/visualization.py",
    "src/urban_morphology/workflow.py",
]


def unique_stage_root() -> Path:
    stamp = int(time.time() * 1000)
    return PROJECT_ROOT / "_release" / f"stability_release_stage_{stamp}_{os.getpid()}"


def assert_required_files(stage_root: Path) -> list[str]:
    return [rel for rel in REQUIRED_STAGE_FILES if not (stage_root / rel).exists()]


def compile_staged_core(stage_root: Path) -> dict[str, Any]:
    command = [sys.executable, "-m", "py_compile", *STAGED_COMPILE_FILES]
    proc = subprocess.run(
        command,
        cwd=stage_root,
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "command": command,
        "returncode": proc.returncode,
        "stdout_tail": proc.stdout[-2000:],
        "stderr_tail": proc.stderr[-2000:],
    }


def main() -> None:
    stage_root = unique_stage_root()
    result: dict[str, Any] = {
        "status": "failed",
        "stage_root": str(stage_root),
        "required_file_count": len(REQUIRED_STAGE_FILES),
    }
    try:
        manifest = prepare(stage_root, "outputs_citylbm_voxel_china/dalian_dlut_west_library", include_large_assets=False)
        missing = assert_required_files(stage_root)
        compile_result = compile_staged_core(stage_root)
        result.update(
            {
                "manifest_status": manifest.get("status"),
                "file_count": manifest.get("file_count"),
                "total_bytes": manifest.get("total_bytes"),
                "missing_required_files": missing,
                "staged_compile": compile_result,
            }
        )
        if not missing and compile_result["returncode"] == 0:
            result["status"] = "success"
    except Exception as exc:
        result["error"] = repr(exc)

    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
