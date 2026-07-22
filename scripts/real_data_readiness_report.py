from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from china_voxel_pipeline import OUTPUT_ROOT, write_json  # noqa: E402
from plan_worldcover_tiles import ManifestSite, plan_worldcover_tiles  # noqa: E402
from preflight_site_data_sources import preflight  # noqa: E402
from run_site_model import build_request  # noqa: E402
from validate_dem_cache import site_dem_cache_paths, validate_dem_caches  # noqa: E402
from validate_osm_cache import site_cache_paths as osm_site_cache_paths  # noqa: E402
from validate_osm_cache import validate_osm_caches  # noqa: E402
from validate_worldcover_tiles import validate_manifest  # noqa: E402


def request_namespace(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=args.site_name,
        site_name_cn=args.site_name_cn or args.site_name,
        lat=args.lat,
        lon=args.lon,
        input_crs=args.input_crs,
        half_size_m=args.half_size_m,
        voxel_size_m=args.voxel_size_m,
        output_root=args.output_root,
    )


def preflight_namespace(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=args.site_name,
        site_name_cn=args.site_name_cn or args.site_name,
        lat=args.lat,
        lon=args.lon,
        input_crs=args.input_crs,
        half_size_m=args.half_size_m,
        voxel_size_m=args.voxel_size_m,
        output_root=args.output_root,
        check_dem_remote=False,
        dem_timeout_s=args.dem_timeout_s,
        check_osm_remote=False,
        osm_timeout_s=args.osm_timeout_s,
        strict=True,
    )


def component_status(status: str, success_values: set[str]) -> str:
    return "passed" if status in success_values else "failed"


def compact_worldcover(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "tile_count": report.get("tile_count"),
        "valid_tile_count": report.get("valid_tile_count"),
        "missing_tile_count": report.get("missing_tile_count"),
        "invalid_tile_count": report.get("invalid_tile_count"),
        "unchecked_tile_count": report.get("unchecked_tile_count"),
        "missing_tiles": report.get("missing_tiles"),
        "invalid_tiles": report.get("invalid_tiles"),
        "output_json": report.get("output_json"),
    }


def compact_dem(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "required_tile_count": report.get("required_tile_count"),
        "satisfied_tile_count": report.get("satisfied_tile_count"),
        "valid_cache_count": report.get("valid_cache_count"),
        "invalid_cache_count": report.get("invalid_cache_count"),
        "missing_cache_count": report.get("missing_cache_count"),
        "missing_tiles": report.get("missing_tiles"),
        "invalid_tiles": report.get("invalid_tiles"),
        "elevation_summary": report.get("elevation_summary"),
        "output_json": report.get("output_json"),
    }


def compact_osm(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": report.get("status"),
        "valid_cache_count": report.get("valid_cache_count"),
        "invalid_cache_count": report.get("invalid_cache_count"),
        "missing_cache_count": report.get("missing_cache_count"),
        "selected_cache": report.get("selected_cache"),
        "selected_counts": report.get("selected_counts"),
        "output_json": report.get("output_json"),
    }


def build_readiness_report(args: argparse.Namespace) -> dict[str, Any]:
    request = build_request(request_namespace(args))
    output_root = Path(request.output_root)
    logs_dir = output_root / "12_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    effective_args = argparse.Namespace(**vars(args))
    effective_args.site_name = request.site_name
    effective_args.site_name_cn = request.site_name_cn
    effective_args.lat = request.center_lat_wgs84
    effective_args.lon = request.center_lon_wgs84
    effective_args.input_crs = "WGS84"
    effective_args.output_root = request.output_root

    preflight_report = preflight(preflight_namespace(effective_args))
    worldcover_manifest = plan_worldcover_tiles(
        [ManifestSite(request.site_name, request.center_lat_wgs84, request.center_lon_wgs84, request.half_size_m)],
        args.worldcover_path,
        request.output_root,
    )
    worldcover_report = validate_manifest(
        Path(worldcover_manifest["output_json"]),
        logs_dir / "worldcover_tile_validation_for_readiness.json",
        strict=True,
        tolerance=args.worldcover_bounds_tolerance_deg,
    )
    dem_report = validate_dem_caches(
        site_dem_cache_paths(effective_args),
        logs_dir / "dem_cache_validation_for_readiness.json",
        strict=True,
        min_bytes=args.dem_min_bytes,
        max_abs_elevation_m=args.dem_max_abs_elevation_m,
    )
    osm_report = validate_osm_caches(
        osm_site_cache_paths(effective_args),
        logs_dir / "osm_cache_validation_for_readiness.json",
        strict=True,
        require_core_features=not args.allow_no_osm_core_features,
    )

    component_results = {
        "preflight": component_status(preflight_report.get("status"), {"passed", "passed_with_warnings"}),
        "worldcover": component_status(worldcover_report.get("status"), {"success"}),
        "dem": component_status(dem_report.get("status"), {"success"}),
        "osm": component_status(osm_report.get("status"), {"success"}),
    }
    failed_components = [name for name, status in component_results.items() if status != "passed"]
    status = "ready" if not failed_components else "not_ready"
    result = {
        "status": status,
        "strict": bool(args.strict),
        "request": asdict(request),
        "failed_components": failed_components,
        "component_results": component_results,
        "preflight": {
            "status": preflight_report.get("status"),
            "failures": preflight_report.get("failures"),
            "warnings": preflight_report.get("warnings"),
            "worldcover_status": preflight_report.get("worldcover", {}).get("selection_status"),
            "dem_status": preflight_report.get("dem", {}).get("status"),
            "osm_status": preflight_report.get("osm", {}).get("status"),
            "rhino_base": preflight_report.get("rhino_base"),
            "grid": preflight_report.get("grid"),
        },
        "worldcover": compact_worldcover(worldcover_report),
        "dem": compact_dem(dem_report),
        "osm": compact_osm(osm_report),
        "outputs": {
            "report_json": str(logs_dir / "real_data_readiness_report.json"),
            "worldcover_manifest_json": worldcover_manifest.get("output_json"),
            "worldcover_manifest_csv": worldcover_manifest.get("output_csv"),
            "worldcover_gee_js": worldcover_manifest.get("output_gee_js"),
        },
    }
    write_json(logs_dir / "real_data_readiness_report.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Build one formal real-data readiness report before VoxCity/Rhino modeling.")
    parser.add_argument("--site-name", required=True, help="ASCII-safe site id.")
    parser.add_argument("--site-name-cn", default="", help="Human-readable site name.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--input-crs", default="WGS84", choices=["WGS84", "EPSG:4326", "GCJ02", "GCJ-02", "AMAP", "GAODE"])
    parser.add_argument("--half-size-m", type=float, default=250.0)
    parser.add_argument("--voxel-size-m", type=float, default=1.0)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--worldcover-path", default="")
    parser.add_argument("--worldcover-bounds-tolerance-deg", type=float, default=1e-6)
    parser.add_argument("--dem-min-bytes", type=int, default=1024)
    parser.add_argument("--dem-max-abs-elevation-m", type=float, default=9000.0)
    parser.add_argument("--dem-timeout-s", type=int, default=10)
    parser.add_argument("--osm-timeout-s", type=int, default=10)
    parser.add_argument("--allow-no-osm-core-features", action="store_true")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when any readiness component fails.")
    args = parser.parse_args()

    result = build_readiness_report(args)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(1 if args.strict and result["status"] != "ready" else 0)


if __name__ == "__main__":
    main()
