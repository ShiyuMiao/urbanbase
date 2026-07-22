from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PYTHON = Path(sys.executable)
REFERENCE_SITE = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "dlut_arch_art_college_500m_0p1m"
REFERENCE_SITE_LAT = 38.88024056122594
REFERENCE_SITE_LON = 121.52153023152763
REFERENCE_SITE_AOI_WIDTH_M = 500.0
REFERENCE_SITE_VOXEL_SIZE_M = 0.1
DALIAN_LIBRARY_SITE = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "dalian_dlut_west_library"
DALIAN_LIBRARY_SITE_LAT = 38.8831553
DALIAN_LIBRARY_SITE_LON = 121.5120457
DALIAN_LIBRARY_SITE_AOI_WIDTH_M = 500.0
DALIAN_LIBRARY_SITE_VOXEL_SIZE_M = 1.0


def skipped_check(label: str, reason: str) -> dict[str, Any]:
    return {
        "label": label,
        "command": [],
        "status": "skipped",
        "returncode": None,
        "seconds": 0.0,
        "stdout_tail": "",
        "stderr_tail": "",
        "failure_reason": reason,
    }


def parse_last_json_object(text: str) -> dict[str, Any] | None:
    decoder = json.JSONDecoder()
    parsed: dict[str, Any] | None = None
    idx = 0
    while idx < len(text):
        start = text.find("{", idx)
        if start == -1:
            break
        try:
            value, end = decoder.raw_decode(text[start:])
        except json.JSONDecodeError:
            idx = start + 1
            continue
        if isinstance(value, dict):
            parsed = value
        idx = start + end
    return parsed


def compact_parsed_summary(label: str, parsed: dict[str, Any] | None) -> dict[str, Any] | None:
    if not parsed:
        return None
    if label in {"reference_site_output_qa", "dalian_library_formal_output_qa"}:
        return {
            "qa_status": parsed.get("status"),
            "warnings": parsed.get("warnings"),
            "optional_missing": parsed.get("optional_missing"),
            "rhino_summary": parsed.get("rhino_summary"),
            "semantic_layer_summary": parsed.get("semantic_layer_summary"),
            "table_rows": parsed.get("table_rows"),
            "table_schema_summary": parsed.get("table_schema_summary"),
            "table_value_summary": parsed.get("table_value_summary"),
            "site_consistency": parsed.get("site_consistency"),
            "quality_status": parsed.get("quality_status"),
            "preview_image_summary": parsed.get("preview_image_summary"),
        }
    if label == "site_runner_and_qa_smoke":
        return {
            "status": parsed.get("status"),
            "coordinate_normalization": parsed.get("coordinate_normalization"),
            "minimal_qa_bundle": parsed.get("minimal_qa_bundle"),
            "dynamic_rhino_name": parsed.get("dynamic_rhino_name"),
            "strict_real_data_default": parsed.get("strict_real_data_default"),
            "existing_output": parsed.get("existing_output"),
        }
    if label == "cross_china_coordinate_preflight":
        return {
            "status": parsed.get("status"),
            "case_count": parsed.get("case_count"),
            "invalid_input_rejections": parsed.get("invalid_input_rejections"),
        }
    if label == "release_staging_integrity":
        staged_compile = parsed.get("staged_compile", {})
        return {
            "status": parsed.get("status"),
            "stage_root": parsed.get("stage_root"),
            "file_count": parsed.get("file_count"),
            "required_file_count": parsed.get("required_file_count"),
            "missing_required_files": parsed.get("missing_required_files"),
            "staged_compile_returncode": staged_compile.get("returncode"),
        }
    if label == "worldcover_selection":
        return {
            "status": parsed.get("status"),
            "errors": parsed.get("errors"),
            "dalian_expected_tiles": parsed.get("dalian_expected_tiles"),
            "dalian_selection_status": parsed.get("dalian_selection", {}).get("selection_status"),
            "beijing_expected_tiles": parsed.get("beijing_expected_tiles"),
            "beijing_selection_status": parsed.get("beijing_selection", {}).get("selection_status"),
        }
    if label == "worldcover_coverage_audit":
        return {
            "status": parsed.get("status"),
            "candidate_count": parsed.get("candidate_count"),
            "covered_site_count": parsed.get("covered_site_count"),
            "missing_site_count": parsed.get("missing_site_count"),
            "missing_expected_tiles": parsed.get("missing_expected_tiles"),
            "output_json": parsed.get("output_json"),
        }
    if label == "worldcover_tile_manifest":
        return {
            "status": parsed.get("status"),
            "site_count": parsed.get("site_count"),
            "covered_site_count": parsed.get("covered_site_count"),
            "missing_site_count": parsed.get("missing_site_count"),
            "missing_tile_count": parsed.get("missing_tile_count"),
            "missing_expected_tiles": parsed.get("missing_expected_tiles"),
            "output_json": parsed.get("output_json"),
            "output_csv": parsed.get("output_csv"),
            "output_gee_js": parsed.get("output_gee_js"),
        }
    if label == "worldcover_tile_validation":
        return {
            "status": parsed.get("status"),
            "validation_status": parsed.get("validation_status"),
            "strict_validation_status": parsed.get("strict_validation_status"),
            "valid_tile_count": parsed.get("valid_tile_count"),
            "missing_tile_count": parsed.get("missing_tile_count"),
            "missing_tiles": parsed.get("missing_tiles"),
            "output_json": parsed.get("output_json"),
        }
    if label == "osm_cache_validation":
        return {
            "status": parsed.get("status"),
            "valid_cache_count": parsed.get("valid_cache_count"),
            "invalid_cache_count": parsed.get("invalid_cache_count"),
            "missing_cache_count": parsed.get("missing_cache_count"),
            "selected_cache": parsed.get("selected_cache"),
            "selected_counts": parsed.get("selected_counts") or parsed.get("valid_counts"),
            "output_json": parsed.get("output_json"),
        }
    if label == "dem_cache_validation":
        return {
            "status": parsed.get("status"),
            "required_tile_count": parsed.get("required_tile_count"),
            "satisfied_tile_count": parsed.get("satisfied_tile_count"),
            "valid_cache_count": parsed.get("valid_cache_count"),
            "invalid_cache_count": parsed.get("invalid_cache_count"),
            "missing_cache_count": parsed.get("missing_cache_count"),
            "elevation_summary": parsed.get("elevation_summary"),
            "output_json": parsed.get("output_json"),
        }
    if label == "real_data_readiness_report":
        return {
            "status": parsed.get("status"),
            "errors": parsed.get("errors"),
            "dalian": parsed.get("dalian"),
            "beijing": parsed.get("beijing"),
        }
    if label == "site_data_preflight":
        return {
            "status": parsed.get("status"),
            "errors": parsed.get("errors"),
            "dalian": parsed.get("dalian"),
            "beijing": parsed.get("beijing"),
            "shared_osm_cache": parsed.get("shared_osm_cache"),
        }
    if label == "dalian_library_real_data_preflight":
        return {
            "status": parsed.get("status"),
            "failures": parsed.get("failures"),
            "warnings": parsed.get("warnings"),
            "worldcover_status": parsed.get("worldcover", {}).get("selection_status"),
            "dem_status": parsed.get("dem", {}).get("status"),
            "osm_status": parsed.get("osm", {}).get("status"),
            "osm_counts": parsed.get("osm", {}).get("counts"),
            "rhino_base": parsed.get("rhino_base"),
        }
    if label == "site_data_prepare":
        return {
            "status": parsed.get("status"),
            "errors": parsed.get("errors"),
            "dalian": parsed.get("dalian"),
            "beijing": parsed.get("beijing"),
        }
    if label == "morphology_lcz_risk_regression":
        return {
            "status": parsed.get("status"),
            "grid_count": parsed.get("grid_count"),
            "morphology_columns": parsed.get("morphology_columns"),
            "lcz_confidence_counts": parsed.get("lcz_confidence_counts"),
            "risk_level_counts": parsed.get("risk_level_counts"),
            "typical_block_count": parsed.get("typical_block_count"),
            "quality_status": parsed.get("quality_status"),
        }
    if label == "sequential_notebooks":
        return {
            "status": parsed.get("status"),
            "executed_cell_count": parsed.get("executed_cell_count"),
            "failures": parsed.get("failures"),
        }
    if label == "tiny_site_end_to_end":
        qa = parsed.get("qa", {})
        request = parsed.get("request", {})
        return {
            "status": parsed.get("status"),
            "site_name": request.get("site_name"),
            "output_root": request.get("output_root"),
            "qa_status": qa.get("status"),
            "qa_warnings": qa.get("warnings"),
            "qa_optional_missing": qa.get("optional_missing"),
            "rhino_summary": qa.get("rhino_summary"),
            "preview_image_summary": qa.get("preview_image_summary"),
            "table_rows": qa.get("table_rows"),
            "table_schema_summary": qa.get("table_schema_summary"),
            "table_value_summary": qa.get("table_value_summary"),
            "site_consistency": qa.get("site_consistency"),
        }
    if label == "multi_site_end_to_end":
        cases = []
        for case in parsed.get("cases", []):
            cases.append(
                {
                    "site_name": case.get("site_name"),
                    "qa_status": case.get("qa_status"),
                    "qa_warnings": case.get("qa_warnings"),
                    "qa_optional_missing": case.get("qa_optional_missing"),
                    "rhino_summary": case.get("rhino_summary"),
                    "preview_image_summary": case.get("preview_image_summary"),
                    "table_rows": case.get("table_rows"),
                    "table_schema_summary": case.get("table_schema_summary"),
                    "table_value_summary": case.get("table_value_summary"),
                    "feature_counts": case.get("feature_counts"),
                    "quality_thresholds": case.get("quality_thresholds"),
                }
            )
        return {
            "status": parsed.get("status"),
            "output_root": parsed.get("output_root"),
            "site_count": parsed.get("site_count"),
            "passed_site_count": parsed.get("passed_site_count"),
            "failed_sites": parsed.get("failed_sites"),
            "cases": cases,
        }
    if label == "cross_china_e2e_probe":
        cases = []
        for case in parsed.get("cases", []):
            cases.append(
                {
                    "site_name": case.get("site_name"),
                    "status": case.get("status"),
                    "run_class": case.get("run_class"),
                    "source_gaps": case.get("source_gaps"),
                    "feature_counts": case.get("feature_counts"),
                    "real_data_status": case.get("real_data_status"),
                    "error": case.get("error"),
                    "table_rows": case.get("table_rows"),
                    "table_schema_summary": case.get("table_schema_summary"),
                    "table_value_summary": case.get("table_value_summary"),
                }
            )
        return {
            "status": parsed.get("status"),
            "output_root": parsed.get("output_root"),
            "strict_real_data": parsed.get("strict_real_data"),
            "site_count": parsed.get("site_count"),
            "completed_site_count": parsed.get("completed_site_count"),
            "hard_failed_sites": parsed.get("hard_failed_sites"),
            "source_gap_sites": parsed.get("source_gap_sites"),
            "cases": cases,
        }
    return {"status": parsed.get("status")} if "status" in parsed else None


def run_command(label: str, command: list[str], timeout_s: int | None = None) -> dict[str, Any]:
    started = time.time()
    try:
        proc = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout_s,
        )
        elapsed = round(time.time() - started, 3)
        parsed = parse_last_json_object(proc.stdout)
        return {
            "label": label,
            "command": command,
            "status": "passed" if proc.returncode == 0 else "failed",
            "returncode": proc.returncode,
            "seconds": elapsed,
            "stdout_tail": proc.stdout[-4000:],
            "stderr_tail": proc.stderr[-4000:],
            "failure_reason": None if proc.returncode == 0 else "nonzero_exit",
            "parsed_summary": compact_parsed_summary(label, parsed),
        }
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.time() - started, 3)
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        return {
            "label": label,
            "command": command,
            "status": "failed",
            "returncode": None,
            "seconds": elapsed,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
            "failure_reason": f"timeout_after_{timeout_s}s",
            "parsed_summary": compact_parsed_summary(label, parse_last_json_object(stdout)),
        }
    except Exception as exc:  # pragma: no cover - defensive reporting path
        elapsed = round(time.time() - started, 3)
        return {
            "label": label,
            "command": command,
            "status": "failed",
            "returncode": None,
            "seconds": elapsed,
            "stdout_tail": "",
            "stderr_tail": repr(exc),
            "failure_reason": "runner_exception",
            "parsed_summary": None,
        }


def has_soft_warning(result: dict[str, Any]) -> bool:
    parsed = result.get("parsed_summary") or {}
    if parsed.get("status") in {"completed_with_source_gaps", "completed_with_missing_tiles", "passed_with_warnings"}:
        return True
    if parsed.get("source_gap_sites"):
        return True
    return False


def has_worldcover_coverage_gap(result: dict[str, Any]) -> bool:
    if result.get("label") != "worldcover_coverage_audit":
        return False
    parsed = result.get("parsed_summary") or {}
    if parsed.get("status") == "completed_with_missing_tiles":
        return True
    return bool(parsed.get("missing_expected_tiles"))


def warning_labels_excluding_failures(soft_warned: list[dict[str, Any]], hard_failed: list[dict[str, Any]]) -> list[str]:
    failed_labels = {item["label"] for item in hard_failed}
    return [item["label"] for item in soft_warned if item["label"] not in failed_labels]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run project stability checks for the urbanbase/VoxCity workflow.")
    parser.add_argument("--include-tiny-e2e", action="store_true", help="Also run a real tiny AOI end-to-end pipeline.")
    parser.add_argument("--include-multi-site-e2e", action="store_true", help="Also run real multi-site AOI end-to-end smoke tests.")
    parser.add_argument("--include-cross-china-e2e", action="store_true", help="Also run cross-China small AOI E2E probes in preview mode with source-gap reporting.")
    parser.add_argument("--strict-cross-china-real-data", action="store_true", help="Run cross-China probes in strict real-data mode.")
    parser.add_argument("--strict-worldcover-coverage", action="store_true", help="Fail if the cross-site ESA WorldCover coverage audit reports missing tiles.")
    parser.add_argument("--skip-reference-site", action="store_true", help="Skip QA for the existing 500 m reference output.")
    parser.add_argument("--skip-morphology", action="store_true", help="Skip morphology/LCZ/risk regression.")
    parser.add_argument("--timeout-s", type=int, default=180)
    args = parser.parse_args()

    checks: list[tuple[str, list[str]]] = [
        (
            "py_compile_core_scripts",
            [
                str(PYTHON),
                "-m",
                "py_compile",
                "scripts/run_site_model.py",
                "scripts/audit_git_release_status.py",
                "scripts/test_git_release_status_audit.py",
                "scripts/qa_site_output.py",
                "scripts/test_site_model_runner_and_qa.py",
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
                "scripts/test_release_staging_integrity.py",
                "scripts/test_morphology_lcz_risk_workflow.py",
                "scripts/test_sequential_notebooks.py",
                "scripts/test_tiny_site_e2e.py",
                "scripts/test_multi_site_e2e.py",
                "scripts/backfill_site_model_summary.py",
                "scripts/run_stability_checks.py",
                "src/urban_morphology/grid.py",
                "src/urban_morphology/indicators.py",
                "src/urban_morphology/lcz.py",
                "src/urban_morphology/quality.py",
                "src/urban_morphology/risk.py",
                "src/urban_morphology/typical_blocks.py",
                "src/urban_morphology/visualization.py",
                "src/urban_morphology/workflow.py",
            ],
        ),
        ("site_runner_and_qa_smoke", [str(PYTHON), "scripts/test_site_model_runner_and_qa.py"]),
        ("cross_china_coordinate_preflight", [str(PYTHON), "scripts/test_cross_china_coordinate_preflight.py"]),
        ("worldcover_selection", [str(PYTHON), "scripts/test_worldcover_selection.py"]),
        ("worldcover_coverage_audit", [str(PYTHON), "scripts/audit_worldcover_coverage.py"]),
        ("stability_worldcover_gate", [str(PYTHON), "scripts/test_stability_worldcover_gate.py"]),
        ("worldcover_tile_manifest", [str(PYTHON), "scripts/test_worldcover_tile_manifest.py"]),
        ("worldcover_tile_validation", [str(PYTHON), "scripts/test_worldcover_tile_validation.py"]),
        ("osm_cache_validation", [str(PYTHON), "scripts/test_osm_cache_validation.py"]),
        ("dem_cache_validation", [str(PYTHON), "scripts/test_dem_cache_validation.py"]),
        ("real_data_readiness_report", [str(PYTHON), "scripts/test_real_data_readiness_report.py"]),
        ("site_data_preflight", [str(PYTHON), "scripts/test_site_data_preflight.py"]),
        (
            "dalian_library_real_data_preflight",
            [
                str(PYTHON),
                "scripts/preflight_site_data_sources.py",
                "--site-name",
                "dalian_dlut_west_library",
                "--site-name-cn",
                "dalian_dlut_west_library",
                "--lat",
                "38.8831553",
                "--lon",
                "121.5120457",
                "--voxel-size-m",
                "1.0",
                "--strict",
            ],
        ),
        ("site_data_prepare", [str(PYTHON), "scripts/test_prepare_site_data_sources.py"]),
        ("git_release_status_audit", [str(PYTHON), "scripts/test_git_release_status_audit.py"]),
        ("release_staging_integrity", [str(PYTHON), "scripts/test_release_staging_integrity.py"]),
    ]
    if not args.skip_reference_site and REFERENCE_SITE.exists():
        checks.append(
            (
                "reference_site_output_qa",
                [
                    str(PYTHON),
                    "scripts/qa_site_output.py",
                    "--output-root",
                    str(REFERENCE_SITE),
                    "--min-buildings",
                    "1",
                    "--min-green-features",
                    "1",
                    "--min-dem-relief-m",
                    "1.0",
                    "--expected-lat",
                    str(REFERENCE_SITE_LAT),
                    "--expected-lon",
                    str(REFERENCE_SITE_LON),
                    "--expected-aoi-width-m",
                    str(REFERENCE_SITE_AOI_WIDTH_M),
                    "--expected-voxel-size-m",
                    str(REFERENCE_SITE_VOXEL_SIZE_M),
                    "--require-layer-token",
                    "Buildings_",
                    "--require-layer-token",
                    "Roads_Hardscape_",
                    "--require-layer-token",
                    "Green_Trees_",
                    "--require-layer-token",
                    "Green_Grass_",
                    "--require-layer-token",
                    "Terrain_DEM_",
                    "--require-real-data-sources",
                ],
            )
        )
    if not args.skip_reference_site and DALIAN_LIBRARY_SITE.exists():
        checks.append(
            (
                "dalian_library_formal_output_qa",
                [
                    str(PYTHON),
                    "scripts/qa_site_output.py",
                    "--output-root",
                    str(DALIAN_LIBRARY_SITE),
                    "--min-buildings",
                    "1",
                    "--min-green-features",
                    "1",
                    "--min-dem-relief-m",
                    "1.0",
                    "--expected-lat",
                    str(DALIAN_LIBRARY_SITE_LAT),
                    "--expected-lon",
                    str(DALIAN_LIBRARY_SITE_LON),
                    "--expected-aoi-width-m",
                    str(DALIAN_LIBRARY_SITE_AOI_WIDTH_M),
                    "--expected-voxel-size-m",
                    str(DALIAN_LIBRARY_SITE_VOXEL_SIZE_M),
                    "--require-layer-token",
                    "Buildings_",
                    "--require-layer-token",
                    "Roads_Hardscape_",
                    "--require-layer-token",
                    "Green_Trees_",
                    "--require-layer-token",
                    "Green_Grass_",
                    "--require-layer-token",
                    "Terrain_DEM_",
                    "--require-real-data-sources",
                    "--require-readiness-check",
                ],
            )
        )
    if not args.skip_morphology:
        checks.append(("morphology_lcz_risk_regression", [str(PYTHON), "scripts/test_morphology_lcz_risk_workflow.py"]))
        checks.append(("sequential_notebooks", [str(PYTHON), "scripts/test_sequential_notebooks.py"]))
    if args.include_tiny_e2e:
        checks.append(("tiny_site_end_to_end", [str(PYTHON), "scripts/test_tiny_site_e2e.py"]))
    if args.include_multi_site_e2e:
        checks.append(("multi_site_end_to_end", [str(PYTHON), "scripts/test_multi_site_e2e.py"]))
    if args.include_cross_china_e2e:
        command = [str(PYTHON), "scripts/test_cross_china_e2e_probe.py", "--skip-render"]
        if args.strict_cross_china_real_data:
            command.append("--strict-real-data")
        checks.append(("cross_china_e2e_probe", command))

    results = [run_command(label, command, timeout_s=args.timeout_s) for label, command in checks]
    if not args.skip_reference_site and not REFERENCE_SITE.exists():
        results.append(skipped_check("reference_site_output_qa", f"missing_reference_site:{REFERENCE_SITE}"))
    if not args.skip_reference_site and not DALIAN_LIBRARY_SITE.exists():
        results.append(skipped_check("dalian_library_formal_output_qa", f"missing_reference_site:{DALIAN_LIBRARY_SITE}"))
    hard_failed = [item for item in results if item["status"] == "failed"]
    soft_warned = [item for item in results if has_soft_warning(item)]
    strict_failed = [item for item in results if args.strict_worldcover_coverage and has_worldcover_coverage_gap(item)]
    hard_failed_labels = {item["label"] for item in hard_failed}
    for item in strict_failed:
        if item["label"] not in hard_failed_labels:
            hard_failed.append(item)
            hard_failed_labels.add(item["label"])
    summary = {
        "status": "passed" if not hard_failed else "failed",
        "project_root": str(PROJECT_ROOT),
        "python": str(PYTHON),
        "include_tiny_e2e": args.include_tiny_e2e,
        "include_multi_site_e2e": args.include_multi_site_e2e,
        "include_cross_china_e2e": args.include_cross_china_e2e,
        "strict_cross_china_real_data": args.strict_cross_china_real_data,
        "strict_worldcover_coverage": args.strict_worldcover_coverage,
        "skip_reference_site": args.skip_reference_site,
        "skip_morphology": args.skip_morphology,
        "timeout_s": args.timeout_s,
        "failed_checks": [item["label"] for item in hard_failed],
        "warning_checks": warning_labels_excluding_failures(soft_warned, hard_failed),
        "skipped_checks": [item["label"] for item in results if item["status"] == "skipped"],
        "checks": results,
    }
    out_path = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "12_logs" / "stability_checks_summary.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json = json.dumps(summary, ensure_ascii=True, indent=2)
    out_path.write_text(summary_json, encoding="utf-8")
    print(summary_json)
    raise SystemExit(0 if summary["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
