from __future__ import annotations

import argparse
import csv
import json
import sys
from dataclasses import asdict, dataclass
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
class SiteCase:
    site_name: str
    site_name_cn: str
    lat: float
    lon: float
    input_crs: str
    min_buildings: int
    min_roads: int
    min_green: int
    min_water: int
    min_elevation_range_m: float
    min_rhino_objects: int


SITE_CASES = [
    SiteCase(
        site_name="dlut_arch_art_compact_campus",
        site_name_cn="DUT Architecture and Art College compact campus",
        lat=38.881098,
        lon=121.526615,
        input_crs="GCJ02",
        min_buildings=1,
        min_roads=1,
        min_green=1,
        min_water=0,
        min_elevation_range_m=1.0,
        min_rhino_objects=4,
    ),
    SiteCase(
        site_name="dalian_zhongshan_square_dense_urban",
        site_name_cn="Dalian Zhongshan Square dense urban",
        lat=38.9188,
        lon=121.6438,
        input_crs="WGS84",
        min_buildings=1,
        min_roads=1,
        min_green=0,
        min_water=0,
        min_elevation_range_m=1.0,
        min_rhino_objects=4,
    ),
    SiteCase(
        site_name="dalian_lianhuashan_park_hilly_green",
        site_name_cn="Dalian Lianhuashan Park hilly green",
        lat=38.8877,
        lon=121.6139,
        input_crs="WGS84",
        min_buildings=0,
        min_roads=1,
        min_green=1,
        min_water=0,
        min_elevation_range_m=5.0,
        min_rhino_objects=4,
    ),
    SiteCase(
        site_name="dalian_xinghai_bay_water_edge",
        site_name_cn="Dalian Xinghai Bay water edge",
        lat=38.8730,
        lon=121.5880,
        input_crs="WGS84",
        min_buildings=0,
        min_roads=0,
        min_green=0,
        min_water=1,
        min_elevation_range_m=0.0,
        min_rhino_objects=4,
    ),
]


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "outputs_citylbm_voxel_china" / f"_smoke_multi_site_e2e_{stamp}"


def voxel_size_slug(voxel_size_m: float) -> str:
    text = f"{float(voxel_size_m):g}".replace("-", "m")
    return f"{text.replace('.', 'p')}m"


def read_basic_stats(path: Path) -> dict[str, Any]:
    stats_path = path / "06_tables" / "basic_site_statistics.csv"
    result: dict[str, Any] = {}
    if not stats_path.exists():
        return result
    with stats_path.open("r", encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            key = f"{row.get('category')}.{row.get('metric')}"
            result[key] = row.get("value")
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


def validate_case_quality(case: SiteCase, stats: dict[str, Any], rhino_summary: dict[str, Any]) -> dict[str, Any]:
    observed = {
        "building_count": as_int(stats.get("features.building_count")),
        "road_count": as_int(stats.get("features.road_count")),
        "green_count": as_int(stats.get("features.green_count")),
        "water_count": as_int(stats.get("features.water_count")),
        "elevation_range_m": as_float(stats.get("dem.elevation_range_m")),
        "rhino_object_count": as_int(rhino_summary.get("object_count")),
    }
    expected = {
        "min_buildings": case.min_buildings,
        "min_roads": case.min_roads,
        "min_green": case.min_green,
        "min_water": case.min_water,
        "min_elevation_range_m": case.min_elevation_range_m,
        "min_rhino_objects": case.min_rhino_objects,
    }
    errors: list[str] = []
    if observed["building_count"] < case.min_buildings:
        errors.append(f"building_count {observed['building_count']} < {case.min_buildings}")
    if observed["road_count"] < case.min_roads:
        errors.append(f"road_count {observed['road_count']} < {case.min_roads}")
    if observed["green_count"] < case.min_green:
        errors.append(f"green_count {observed['green_count']} < {case.min_green}")
    if observed["water_count"] < case.min_water:
        errors.append(f"water_count {observed['water_count']} < {case.min_water}")
    if observed["elevation_range_m"] < case.min_elevation_range_m:
        errors.append(f"elevation_range_m {observed['elevation_range_m']} < {case.min_elevation_range_m}")
    if observed["rhino_object_count"] < case.min_rhino_objects:
        errors.append(f"rhino_object_count {observed['rhino_object_count']} < {case.min_rhino_objects}")
    return {
        "status": "passed" if not errors else "failed",
        "expected": expected,
        "observed": observed,
        "errors": errors,
    }


def validate_layer_suffix(output_root: Path, voxel_size_m: float) -> None:
    slug = voxel_size_slug(voxel_size_m)
    expected_layers = {
        f"01_Buildings_{slug}_Voxels",
        f"02_Roads_Hardscape_{slug}_Voxels",
        f"03_Water_{slug}_Voxels",
        f"04_Green_Trees_{slug}_Voxels",
        f"05_Green_Grass_{slug}_Voxels",
        f"06_Terrain_DEM_{slug}_Voxels",
    }
    layer_csv = output_root / "05_rhino" / f"final_city_voxel_{slug}_layers.csv"
    layer_text = layer_csv.read_text(encoding="utf-8-sig") if layer_csv.exists() else ""
    missing_layers = sorted(layer for layer in expected_layers if layer not in layer_text)
    if missing_layers:
        raise SystemExit(f"Rhino layer names do not match voxel size {voxel_size_m:g} m for {output_root.name}: {missing_layers}")


def prepare_case_data(request: SiteModelRequest) -> dict[str, Any]:
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
    report = prepare_site_data_sources(prepare_args)
    if report.get("status") == "failed":
        raise SystemExit(f"Multi-site E2E data preparation failed for {request.site_name}: {report.get('failures')}")
    return report


def case_allows_no_osm_core_features(case: SiteCase) -> bool:
    return case.min_buildings == 0 and case.min_roads == 0


def run_case(case: SiteCase, root: Path, half_size_m: float, voxel_size_m: float, render_image: bool) -> dict[str, Any]:
    lon_wgs, lat_wgs = to_wgs84(case.lon, case.lat, case.input_crs)
    output_root = root / case.site_name
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(f"Refusing to run multi-site E2E in non-empty directory: {output_root}")
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
    prepare_report = prepare_case_data(request)
    summary = run_site_model(
        request,
        run_morphology=True,
        render_image=render_image,
        run_qa=True,
        qa_min_buildings=case.min_buildings,
        allow_no_osm_core_features=case_allows_no_osm_core_features(case),
    )
    qa = qa_site_output(
        output_root,
        min_buildings=case.min_buildings,
        expected_lat=lat_wgs,
        expected_lon=lon_wgs,
        expected_aoi_width_m=half_size_m * 2.0,
        expected_voxel_size_m=voxel_size_m,
        require_preview_image=render_image,
    )
    if qa["status"] != "passed":
        raise SystemExit(f"Multi-site E2E QA failed for {case.site_name}: {qa['errors']}")
    expected_rhino = output_root / "05_rhino" / f"final_city_voxel_{voxel_size_slug(voxel_size_m)}.3dm"
    if not expected_rhino.exists():
        raise SystemExit(f"Multi-site E2E did not write expected Rhino file for {case.site_name}: {expected_rhino}")
    validate_layer_suffix(output_root, voxel_size_m)
    stats = read_basic_stats(output_root)
    quality = validate_case_quality(case, stats, qa["rhino_summary"])
    if quality["status"] != "passed":
        raise SystemExit(f"Multi-site E2E quality thresholds failed for {case.site_name}: {quality['errors']}")
    return {
        "site_name": case.site_name,
        "site_name_cn": case.site_name_cn,
        "input_crs": case.input_crs,
        "center_lat_wgs84": lat_wgs,
        "center_lon_wgs84": lon_wgs,
        "output_root": str(output_root),
        "rhino_file": str(expected_rhino),
        "summary_status": summary.get("status"),
        "qa_status": qa["status"],
        "qa_warnings": qa["warnings"],
        "qa_optional_missing": qa["optional_missing"],
        "rhino_summary": qa["rhino_summary"],
        "preview_image_summary": qa["preview_image_summary"],
        "table_rows": qa["table_rows"],
        "table_schema_summary": qa["table_schema_summary"],
        "table_value_summary": qa["table_value_summary"],
        "site_consistency": qa["site_consistency"],
        "data_prepare": {
            "status": prepare_report.get("status"),
            "actions": prepare_report.get("actions"),
            "final_preflight": prepare_report.get("final_preflight"),
        },
        "feature_counts": {
            "building_count": quality["observed"]["building_count"],
            "road_count": quality["observed"]["road_count"],
            "green_count": quality["observed"]["green_count"],
            "water_count": quality["observed"]["water_count"],
            "elevation_range_m": quality["observed"]["elevation_range_m"],
        },
        "quality_thresholds": quality,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run real-data multi-site E2E smoke tests for the site modeling pipeline.")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--half-size-m", type=float, default=30.0)
    parser.add_argument("--voxel-size-m", type=float, default=2.0)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    root = Path(args.output_root) if args.output_root else default_output_root()
    if not root.is_absolute():
        root = PROJECT_ROOT / root
    if root.exists() and any(root.iterdir()):
        raise SystemExit(f"Refusing to run multi-site E2E in non-empty directory: {root}")
    root.mkdir(parents=True, exist_ok=True)

    cases = [
        run_case(
            case=case,
            root=root,
            half_size_m=args.half_size_m,
            voxel_size_m=args.voxel_size_m,
            render_image=not args.skip_render,
        )
        for case in SITE_CASES
    ]
    failed = [case for case in cases if case["qa_status"] != "passed"]
    result = {
        "status": "success" if not failed else "failed",
        "output_root": str(root),
        "half_size_m": args.half_size_m,
        "voxel_size_m": args.voxel_size_m,
        "site_count": len(cases),
        "passed_site_count": len(cases) - len(failed),
        "failed_sites": [case["site_name"] for case in failed],
        "cases": cases,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
