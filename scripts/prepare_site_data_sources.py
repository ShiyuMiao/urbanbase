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

from china_voxel_pipeline import (  # noqa: E402
    RunConfig,
    ensure_dirs,
    fetch_dem_surface,
    fetch_osm_layers,
    load_esa_worldcover_landcover,
    write_json,
)
from preflight_site_data_sources import preflight  # noqa: E402
from run_site_model import build_request  # noqa: E402


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
        check_dem_remote=args.check_dem_remote,
        dem_timeout_s=args.dem_timeout_s,
        check_osm_remote=args.check_osm_remote,
        osm_timeout_s=args.osm_timeout_s,
        strict=args.strict,
    )


def config_from_request(request: Any, strict: bool) -> RunConfig:
    return RunConfig(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        center_lat=request.center_lat_wgs84,
        center_lon=request.center_lon_wgs84,
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        output_root=request.output_root,
        strict_real_data=strict,
    )


def prepare_site_data_sources(args: argparse.Namespace) -> dict[str, Any]:
    request = build_request(request_namespace(args))
    config = config_from_request(request, args.strict)
    dirs = ensure_dirs(config)

    initial_preflight = preflight(preflight_namespace(args))
    actions: dict[str, Any] = {}

    if args.extract_worldcover:
        worldcover = load_esa_worldcover_landcover(config, dirs)
        metadata = worldcover.get("metadata", {})
        actions["worldcover"] = {
            "status": metadata.get("status"),
            "selected_path": metadata.get("path"),
            "green_feature_count": metadata.get("green_feature_count"),
            "water_feature_count": metadata.get("water_feature_count"),
            "tree_feature_count": metadata.get("tree_feature_count"),
            "expected_tiles": metadata.get("expected_tiles") or metadata.get("raster_selection", {}).get("expected_tiles"),
        }

    if args.fetch_dem:
        dem_surface = fetch_dem_surface(config, dirs)
        metadata = dem_surface.get("metadata", {})
        actions["dem"] = {
            "status": metadata.get("status"),
            "source": metadata.get("source"),
            "tile_zoom": metadata.get("tile_zoom"),
            "elevation_range_m": metadata.get("elevation_range_m"),
            "error": metadata.get("error"),
        }

    if args.fetch_osm:
        layers, audit = fetch_osm_layers(config, dirs)
        fetch_audit = audit[0] if audit else {}
        actions["osm"] = {
            "provider": fetch_audit.get("provider"),
            "error": fetch_audit.get("error"),
            "building_count": int(len(layers.get("buildings", []))),
            "road_count": int(len(layers.get("roads", []))),
            "water_count": int(len(layers.get("water", []))),
            "green_count": int(len(layers.get("green", []))),
            "poi_count": int(len(layers.get("poi", []))),
            "raw_cache": fetch_audit.get("raw_cache"),
            "shared_cache": fetch_audit.get("shared_cache"),
        }

    final_preflight = preflight(preflight_namespace(args))
    failures = list(final_preflight.get("failures", []))
    warnings = list(final_preflight.get("warnings", []))
    for name, action in actions.items():
        if action.get("status") in {"fallback_procedural", "missing_raster", "missing_coverage", "missing_dependency"}:
            warnings.append(f"{name} preparation ended with {action.get('status')}.")
        if name == "osm" and action.get("provider") == "fallback_empty":
            warnings.append("OSM preparation ended with fallback_empty.")

    result = {
        "status": "failed" if args.strict and failures else "passed_with_warnings" if warnings else "passed",
        "mode": "prepare" if actions else "check_only",
        "strict": bool(args.strict),
        "request": asdict(request),
        "initial_preflight": {
            "status": initial_preflight.get("status"),
            "failures": initial_preflight.get("failures"),
            "warnings": initial_preflight.get("warnings"),
        },
        "actions": actions,
        "final_preflight": {
            "status": final_preflight.get("status"),
            "worldcover_status": final_preflight.get("worldcover", {}).get("selection_status"),
            "dem_status": final_preflight.get("dem", {}).get("status"),
            "osm_status": final_preflight.get("osm", {}).get("status"),
            "failures": failures,
            "warnings": final_preflight.get("warnings"),
        },
        "failures": failures,
        "warnings": warnings,
    }
    write_json(dirs["logs"] / "site_data_prepare_report.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare or check source data before running the heavy VoxCity modeling pipeline.")
    parser.add_argument("--site-name", required=True, help="ASCII-safe site id.")
    parser.add_argument("--site-name-cn", default="", help="Human-readable site name.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--input-crs", default="WGS84", choices=["WGS84", "EPSG:4326", "GCJ02", "GCJ-02", "AMAP", "GAODE"])
    parser.add_argument("--half-size-m", type=float, default=250.0)
    parser.add_argument("--voxel-size-m", type=float, default=1.0)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required formal data sources are missing.")
    parser.add_argument("--check-dem-remote", action="store_true", help="Probe one required DEM tile URL without caching it.")
    parser.add_argument("--dem-timeout-s", type=int, default=10)
    parser.add_argument("--check-osm-remote", action="store_true", help="Probe Overpass availability with a small query without caching it.")
    parser.add_argument("--osm-timeout-s", type=int, default=10)
    parser.add_argument("--extract-worldcover", action="store_true", help="Crop local ESA WorldCover into green/water vector layers.")
    parser.add_argument("--fetch-dem", action="store_true", help="Download/cache DEM samples for this site.")
    parser.add_argument("--fetch-osm", action="store_true", help="Fetch/cache OSM/Overpass semantic layers for this site.")
    args = parser.parse_args()

    result = prepare_site_data_sources(args)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(1 if result["status"] == "failed" else 0)


if __name__ == "__main__":
    main()
