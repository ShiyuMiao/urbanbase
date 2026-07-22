from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qa_site_output import qa_site_output
from prepare_site_data_sources import prepare_site_data_sources
from run_site_model import SiteModelRequest, run_site_model, to_wgs84


@dataclass(frozen=True)
class ProbeCase:
    site_name: str
    site_name_cn: str
    lat: float
    lon: float
    input_crs: str = "WGS84"


CROSS_CHINA_CASES = [
    ProbeCase("beijing_core_probe", "Beijing core built environment probe", 39.9042, 116.4074),
    ProbeCase("shanghai_core_probe", "Shanghai core built environment probe", 31.2304, 121.4737),
    ProbeCase("chengdu_core_probe", "Chengdu core built environment probe", 30.5728, 104.0668),
    ProbeCase("shenzhen_core_probe", "Shenzhen core built environment probe", 22.5431, 114.0579),
    ProbeCase("urumqi_core_probe", "Urumqi core built environment probe", 43.8256, 87.6168),
    ProbeCase("harbin_core_probe", "Harbin core built environment probe", 45.8038, 126.5349),
]


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "outputs_citylbm_voxel_china" / f"_smoke_cross_china_e2e_{stamp}"


def read_csv_stats(output_root: Path) -> dict[str, Any]:
    path = output_root / "06_tables" / "basic_site_statistics.csv"
    result: dict[str, Any] = {}
    if not path.exists():
        return result
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            result[f"{row.get('category')}.{row.get('metric')}"] = row.get("value")
    return result


def as_int(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def as_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def read_real_data_check(output_root: Path) -> dict[str, Any]:
    path = output_root / "07_audit" / "real_data_source_check.json"
    if not path.exists():
        return {"status": "missing", "checks": {}, "failures": ["real_data_source_check.json is missing"]}
    return json.loads(path.read_text(encoding="utf-8"))


def classify_error(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    lower = text.lower()
    if "strict real-data check failed" in lower:
        return "source_data_gap"
    if "overpass" in lower or "timeout" in lower or "connection" in lower or "http" in lower:
        return "network_or_remote_service"
    if "qa failed" in lower or "quality thresholds" in lower:
        return "quality_gate"
    return "program_error"


def summarize_success(output_root: Path, qa: dict[str, Any], real_data: dict[str, Any]) -> dict[str, Any]:
    stats = read_csv_stats(output_root)
    real_checks = real_data.get("checks", {}) if isinstance(real_data.get("checks", {}), dict) else {}
    source_gaps = [
        key
        for key, value in {
            "dem": real_checks.get("uses_dem_fallback"),
            "worldcover": real_checks.get("uses_worldcover_fallback"),
            "osm": real_checks.get("uses_osm_empty_fallback"),
        }.items()
        if bool(value)
    ]
    return {
        "run_class": "passed_real_data" if not source_gaps else "passed_preview_with_source_gaps",
        "source_gaps": source_gaps,
        "real_data_status": real_data.get("status"),
        "real_data_checks": real_checks,
        "qa_status": qa.get("status"),
        "qa_warnings": qa.get("warnings"),
        "rhino_summary": qa.get("rhino_summary"),
        "feature_counts": {
            "building_count": as_int(stats.get("features.building_count")),
            "road_count": as_int(stats.get("features.road_count")),
            "green_count": as_int(stats.get("features.green_count")),
            "water_count": as_int(stats.get("features.water_count")),
            "elevation_range_m": as_float(stats.get("dem.elevation_range_m")),
        },
        "table_rows": qa.get("table_rows"),
        "table_schema_summary": qa.get("table_schema_summary"),
        "table_value_summary": qa.get("table_value_summary"),
        "site_consistency": qa.get("site_consistency"),
    }


def prepare_probe_data(request: SiteModelRequest) -> dict[str, Any]:
    prepare_args = argparse.Namespace(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        lat=request.input_lat,
        lon=request.input_lon,
        input_crs=request.input_crs,
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        output_root=request.output_root,
        strict=True,
        check_dem_remote=False,
        dem_timeout_s=10,
        check_osm_remote=False,
        osm_timeout_s=10,
        extract_worldcover=False,
        fetch_dem=True,
        fetch_osm=True,
    )
    return prepare_site_data_sources(prepare_args)


def run_probe_case(
    case: ProbeCase,
    root: Path,
    half_size_m: float,
    voxel_size_m: float,
    strict_real_data: bool,
    render_image: bool,
) -> dict[str, Any]:
    lon_wgs, lat_wgs = to_wgs84(case.lon, case.lat, case.input_crs)
    output_root = root / case.site_name
    request = SiteModelRequest(
        site_name=case.site_name,
        site_name_cn=case.site_name_cn,
        input_lat=case.lat,
        input_lon=case.lon,
        input_crs=case.input_crs,
        center_lat_wgs84=lat_wgs,
        center_lon_wgs84=lon_wgs,
        half_size_m=half_size_m,
        voxel_size_m=voxel_size_m,
        output_root=str(output_root),
    )
    base: dict[str, Any] = {
        "site_name": case.site_name,
        "site_name_cn": case.site_name_cn,
        "input_crs": case.input_crs,
        "center_lat_wgs84": lat_wgs,
        "center_lon_wgs84": lon_wgs,
        "output_root": str(output_root),
    }
    try:
        prepare_report = prepare_probe_data(request) if strict_real_data else None
        if prepare_report and prepare_report.get("status") == "failed":
            raise RuntimeError(f"Real-data preparation failed before strict probe: {prepare_report.get('failures')}")
        summary = run_site_model(
            request,
            run_morphology=True,
            render_image=render_image,
            run_qa=True,
            qa_min_buildings=0,
            allow_fallback_preview=not strict_real_data,
        )
        qa = qa_site_output(
            output_root,
            min_buildings=0,
            expected_lat=lat_wgs,
            expected_lon=lon_wgs,
            expected_aoi_width_m=half_size_m * 2.0,
            expected_voxel_size_m=voxel_size_m,
            require_real_data_sources=strict_real_data,
            require_preview_image=render_image,
        )
        if qa["status"] != "passed":
            raise RuntimeError(f"Site output QA failed: {qa['errors']}")
        real_data = read_real_data_check(output_root)
        base.update(
            {
                "status": "completed",
                "summary_status": summary.get("status"),
                "data_prepare": {
                    "status": (prepare_report or {}).get("status"),
                    "actions": (prepare_report or {}).get("actions"),
                    "final_preflight": (prepare_report or {}).get("final_preflight"),
                } if prepare_report else None,
                **summarize_success(output_root, qa, real_data),
            }
        )
    except Exception as exc:
        base.update(
            {
                "status": "failed",
                "run_class": classify_error(exc),
                "error": str(exc),
                "traceback_tail": traceback.format_exc()[-2000:],
            }
        )
        partial_real_data = read_real_data_check(output_root)
        if partial_real_data.get("status") != "missing":
            base["real_data_status"] = partial_real_data.get("status")
            base["real_data_checks"] = partial_real_data.get("checks")
            base["source_failures"] = partial_real_data.get("failures")
    return base


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe small real-data E2E model generation across multiple China cities.")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--half-size-m", type=float, default=30.0)
    parser.add_argument("--voxel-size-m", type=float, default=2.0)
    parser.add_argument("--strict-real-data", action="store_true", help="Fail/classify cases when DEM, WorldCover, or OSM core sources fall back.")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--max-cases", type=int, default=0, help="Limit number of probe cases for quick local checks. 0 means all cases.")
    args = parser.parse_args()

    root = Path(args.output_root) if args.output_root else default_output_root()
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to run cross-China E2E probe in non-empty directory: {root}")
    root.mkdir(parents=True, exist_ok=True)

    cases = CROSS_CHINA_CASES[: args.max_cases] if args.max_cases and args.max_cases > 0 else CROSS_CHINA_CASES
    results = [
        run_probe_case(
            case=case,
            root=root,
            half_size_m=args.half_size_m,
            voxel_size_m=args.voxel_size_m,
            strict_real_data=args.strict_real_data,
            render_image=not args.skip_render,
        )
        for case in cases
    ]
    hard_failures = [case for case in results if case["status"] == "failed" and case["run_class"] not in {"source_data_gap"}]
    source_gap_failures = [case for case in results if case["status"] == "failed" and case["run_class"] == "source_data_gap"]
    preview_source_gaps = [case for case in results if case.get("run_class") == "passed_preview_with_source_gaps"]
    summary = {
        "status": "failed" if hard_failures else "completed_with_source_gaps" if source_gap_failures or preview_source_gaps else "success",
        "output_root": str(root),
        "strict_real_data": bool(args.strict_real_data),
        "half_size_m": args.half_size_m,
        "voxel_size_m": args.voxel_size_m,
        "site_count": len(results),
        "completed_site_count": len([case for case in results if case["status"] == "completed"]),
        "hard_failed_sites": [case["site_name"] for case in hard_failures],
        "source_gap_sites": [case["site_name"] for case in source_gap_failures + preview_source_gaps],
        "cases": results,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not hard_failures else 1)


if __name__ == "__main__":
    main()
