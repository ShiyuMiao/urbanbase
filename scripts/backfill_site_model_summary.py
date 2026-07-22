from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qa_site_output import qa_site_output


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _latest_preview(output_root: Path) -> str | None:
    figures = sorted((output_root / "10_figures").glob("*voxel_model_review.png"))
    return str(figures[-1]) if figures else None


def _morphology_quality_status(output_root: Path) -> str | None:
    path = output_root / "07_audit" / "morphology_lcz_risk_quality_report.json"
    if not path.exists():
        return None
    return _read_json(path).get("status")


def backfill_site_model_summary(
    output_root: str | Path,
    expected_lat: float | None = None,
    expected_lon: float | None = None,
    expected_aoi_width_m: float | None = None,
    expected_voxel_size_m: float | None = None,
    min_buildings: int = 1,
) -> dict[str, Any]:
    output_root = Path(output_root)
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    run_report_path = output_root / "12_logs" / "run_report.json"
    if not run_report_path.exists():
        raise FileNotFoundError(f"Missing run report: {run_report_path}")
    run_report = _read_json(run_report_path)
    config = run_report.get("config", {})
    qa_report = qa_site_output(
        output_root,
        min_buildings=min_buildings,
        expected_lat=expected_lat,
        expected_lon=expected_lon,
        expected_aoi_width_m=expected_aoi_width_m,
        expected_voxel_size_m=expected_voxel_size_m,
    )
    request = {
        "site_name": config.get("site_name"),
        "site_name_cn": config.get("site_name_cn"),
        "input_lat": config.get("center_lat"),
        "input_lon": config.get("center_lon"),
        "input_crs": "WGS84",
        "center_lat_wgs84": config.get("center_lat"),
        "center_lon_wgs84": config.get("center_lon"),
        "half_size_m": config.get("half_size_m"),
        "voxel_size_m": config.get("voxel_size_m"),
        "output_root": str(output_root),
    }
    summary = {
        "status": "success" if qa_report.get("status") == "passed" else "failed",
        "summary_source": "backfilled_from_existing_run_report_and_qa",
        "request": request,
        "rhino_file": run_report.get("rhino_meta", {}).get("file"),
        "pipeline_scene_classification": run_report.get("scene_classification", {}).get("classification", {}),
        "artifact_count": run_report.get("artifact_count"),
        "morphology_quality_status": _morphology_quality_status(output_root),
        "site_output_qa_status": qa_report.get("status"),
        "site_output_qa_errors": qa_report.get("errors"),
        "site_output_qa_warnings": qa_report.get("warnings"),
        "site_output_qa_optional_missing": qa_report.get("optional_missing"),
        "preview_image": _latest_preview(output_root),
    }
    summary_path = output_root / "12_logs" / "site_model_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    final_qa_report = qa_site_output(
        output_root,
        min_buildings=min_buildings,
        expected_lat=expected_lat,
        expected_lon=expected_lon,
        expected_aoi_width_m=expected_aoi_width_m,
        expected_voxel_size_m=expected_voxel_size_m,
    )
    summary["status"] = "success" if final_qa_report.get("status") == "passed" else "failed"
    summary["site_output_qa_status"] = final_qa_report.get("status")
    summary["site_output_qa_errors"] = final_qa_report.get("errors")
    summary["site_output_qa_warnings"] = final_qa_report.get("warnings")
    summary["site_output_qa_optional_missing"] = final_qa_report.get("optional_missing")
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill site_model_summary.json for an existing generated site bundle.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--expected-lat", type=float, default=None)
    parser.add_argument("--expected-lon", type=float, default=None)
    parser.add_argument("--expected-aoi-width-m", type=float, default=None)
    parser.add_argument("--expected-voxel-size-m", type=float, default=None)
    parser.add_argument("--min-buildings", type=int, default=1)
    args = parser.parse_args()
    summary = backfill_site_model_summary(
        args.output_root,
        expected_lat=args.expected_lat,
        expected_lon=args.expected_lon,
        expected_aoi_width_m=args.expected_aoi_width_m,
        expected_voxel_size_m=args.expected_voxel_size_m,
        min_buildings=args.min_buildings,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary["status"] == "success" else 1)


if __name__ == "__main__":
    main()
