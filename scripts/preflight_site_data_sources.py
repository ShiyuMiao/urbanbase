from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "outputs_citylbm_voxel_china"
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from china_voxel_pipeline import (  # noqa: E402
    RunConfig,
    bbox_lonlat,
    ensure_dirs,
    expected_esa_worldcover_tiles,
    grid_config,
    lonlat_to_webmercator_tile,
    osm_shared_cache_path,
    rhino_output_base,
    safe_filename,
    select_esa_worldcover_raster,
    voxel_layer_names,
    write_json,
)
from run_site_model import build_request  # noqa: E402

try:
    import requests
except Exception:  # pragma: no cover - optional dependency report path
    requests = None


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


def config_from_request(request: Any) -> RunConfig:
    return RunConfig(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        center_lat=request.center_lat_wgs84,
        center_lon=request.center_lon_wgs84,
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        output_root=request.output_root,
        strict_real_data=True,
    )


def required_dem_tiles(config: RunConfig, bbox: dict[str, float]) -> list[dict[str, Any]]:
    corners = [
        (bbox["west"], bbox["south"]),
        (bbox["west"], bbox["north"]),
        (bbox["east"], bbox["south"]),
        (bbox["east"], bbox["north"]),
    ]
    tile_coords = [lonlat_to_webmercator_tile(lon, lat, config.dem_tile_zoom)[:2] for lon, lat in corners]
    min_x = min(x for x, _ in tile_coords)
    max_x = max(x for x, _ in tile_coords)
    min_y = min(y for _, y in tile_coords)
    max_y = max(y for _, y in tile_coords)
    tiles: list[dict[str, Any]] = []
    for x in range(min_x, max_x + 1):
        for y in range(min_y, max_y + 1):
            tiles.append({"x": x, "y": y, "zoom": config.dem_tile_zoom})
    return tiles


def probe_dem_tile(tile: dict[str, Any], timeout_s: int) -> dict[str, Any]:
    if requests is None:
        return {"status": "unchecked_missing_requests"}
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{tile['zoom']}/{tile['x']}/{tile['y']}.png"
    try:
        response = requests.get(url, timeout=timeout_s, headers={"User-Agent": "CityLBM-VoxCity preflight"}, stream=True)
        response.raise_for_status()
        return {"status": "remote_available", "url": url, "http_status": response.status_code}
    except Exception as exc:
        return {"status": "remote_unavailable", "url": url, "error": str(exc)}


def dem_preflight(config: RunConfig, dirs: dict[str, Path], bbox: dict[str, float], remote_probe: bool, timeout_s: int) -> dict[str, Any]:
    tiles = required_dem_tiles(config, bbox)
    cache_dir = dirs["cache"] / "dem_tiles" / str(config.dem_tile_zoom)
    cached_count = 0
    shared_cached_count = 0
    tile_reports: list[dict[str, Any]] = []
    for tile in tiles:
        cache_path = cache_dir / f"{tile['x']}_{tile['y']}.png"
        shared_cache_path = DEFAULT_OUTPUT_ROOT / "03_cache" / "dem_tiles" / str(config.dem_tile_zoom) / f"{tile['x']}_{tile['y']}.png"
        cached = cache_path.exists()
        shared_cached = shared_cache_path.exists()
        report = {
            **tile,
            "cache_path": str(cache_path),
            "shared_cache_path": str(shared_cache_path),
            "cached": cached,
            "shared_cached": shared_cached,
        }
        if cached or shared_cached:
            cached_count += 1
        if shared_cached:
            shared_cached_count += 1
        tile_reports.append(report)
    status = "cached_all" if cached_count == len(tiles) else "cached_partial" if cached_count else "not_cached"
    remote_status = None
    if remote_probe and tile_reports:
        remote_status = probe_dem_tile(tile_reports[0], timeout_s)
        if status != "cached_all" and remote_status.get("status") == "remote_available":
            status = "remote_probe_available"
    return {
        "status": status,
        "source": config.dem_source,
        "tile_zoom": config.dem_tile_zoom,
        "required_tile_count": len(tiles),
        "cached_tile_count": cached_count,
        "shared_cached_tile_count": shared_cached_count,
        "remote_probe": remote_status,
        "tiles": tile_reports,
    }


def osm_cache_counts(raw: dict[str, Any]) -> dict[str, int]:
    counts = {
        "element_count": 0,
        "node_count": 0,
        "way_count": 0,
        "building_way_count": 0,
        "highway_way_count": 0,
        "green_way_count": 0,
        "water_way_count": 0,
        "poi_node_count": 0,
    }
    for element in raw.get("elements", []):
        counts["element_count"] += 1
        element_type = element.get("type")
        tags = element.get("tags", {}) or {}
        if element_type == "node":
            counts["node_count"] += 1
            if any(key in tags for key in ("amenity", "shop", "tourism", "public_transport")):
                counts["poi_node_count"] += 1
        elif element_type == "way":
            counts["way_count"] += 1
            if "building" in tags:
                counts["building_way_count"] += 1
            if "highway" in tags:
                counts["highway_way_count"] += 1
            if any(key in tags for key in ("leisure", "landuse", "natural")):
                counts["green_way_count"] += 1
            if tags.get("natural") == "water" or "waterway" in tags:
                counts["water_way_count"] += 1
    return counts


def build_osm_probe_query(bbox: dict[str, float], timeout_s: int) -> str:
    return f"""[out:json][timeout:{timeout_s}];
(
  way({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']})["building"];
  way({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']})["highway"];
);
out ids 20;"""


def probe_overpass(bbox: dict[str, float], timeout_s: int) -> dict[str, Any]:
    if requests is None:
        return {"status": "unchecked_missing_requests"}
    query = build_osm_probe_query(bbox, timeout_s)
    mirrors = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]
    errors: list[str] = []
    for url in mirrors:
        try:
            response = requests.post(
                url,
                data={"data": query},
                timeout=timeout_s,
                headers={"User-Agent": "CityLBM-VoxCity preflight"},
            )
            response.raise_for_status()
            data = response.json()
            return {"status": "remote_available", "provider": url, "returned_element_count": len(data.get("elements", []))}
        except Exception as exc:
            errors.append(f"{url}: {exc}")
    return {"status": "remote_unavailable", "errors": errors}


def osm_preflight(config: RunConfig, dirs: dict[str, Path], bbox: dict[str, float], remote_probe: bool, timeout_s: int) -> dict[str, Any]:
    cache_path = dirs["raw"] / f"osm_overpass_combined_raw_{safe_filename(config.site_name)}.json"
    shared_cache_path = osm_shared_cache_path(config)
    result: dict[str, Any] = {
        "status": "not_cached",
        "cache_path": str(cache_path),
        "shared_cache_path": str(shared_cache_path),
        "cached": cache_path.exists(),
        "shared_cached": shared_cache_path.exists(),
        "remote_probe": None,
        "counts": {},
        "fallback_reason": None,
    }
    readable_cache = cache_path if cache_path.exists() else shared_cache_path if shared_cache_path.exists() else None
    if readable_cache is not None:
        try:
            raw = json.loads(readable_cache.read_text(encoding="utf-8"))
            counts = osm_cache_counts(raw)
            result["counts"] = counts
            result["fallback_reason"] = raw.get("fallback_reason")
            result["cache_used"] = str(readable_cache)
            if raw.get("fallback_reason"):
                result["status"] = "cached_fallback_empty" if readable_cache == cache_path else "shared_cached_fallback_empty"
            elif counts["building_way_count"] or counts["highway_way_count"]:
                result["status"] = "cached_with_core_features" if readable_cache == cache_path else "shared_cached_with_core_features"
            else:
                result["status"] = "cached_without_core_features" if readable_cache == cache_path else "shared_cached_without_core_features"
        except Exception as exc:
            result["status"] = "cached_unreadable" if readable_cache == cache_path else "shared_cached_unreadable"
            result["error"] = str(exc)
    if remote_probe:
        result["remote_probe"] = probe_overpass(bbox, timeout_s)
        if result["status"] == "not_cached" and result["remote_probe"].get("status") == "remote_available":
            result["status"] = "remote_probe_available"
    return result


def preflight(args: argparse.Namespace) -> dict[str, Any]:
    request = build_request(request_namespace(args))
    config = config_from_request(request)
    dirs = ensure_dirs(config)
    bbox = bbox_lonlat(config)
    grid = grid_config(config)
    worldcover = select_esa_worldcover_raster(config, dirs)
    dem = dem_preflight(config, dirs, bbox, args.check_dem_remote, args.dem_timeout_s)
    osm = osm_preflight(config, dirs, bbox, args.check_osm_remote, args.osm_timeout_s)
    layers = voxel_layer_names(config)

    failures: list[str] = []
    warnings: list[str] = []
    if worldcover.get("selection_status") != "selected_intersecting_raster":
        failures.append("ESA WorldCover coverage is missing for this AOI.")
    if dem["status"] not in {"cached_all", "remote_probe_available"}:
        warnings.append("DEM tiles are not fully cached; formal run may need network access.")
    if osm["status"] not in {"cached_with_core_features", "shared_cached_with_core_features", "remote_probe_available"}:
        warnings.append("OSM building/road data are not already available in the current site cache; formal run may need Overpass access.")
    if grid.get("tiled_output"):
        warnings.append("Dense equivalent voxel count exceeds the configured tiling threshold.")

    result = {
        "status": "failed" if args.strict and failures else "passed_with_warnings" if failures or warnings else "passed",
        "strict": bool(args.strict),
        "request": asdict(request),
        "bbox_wgs84": bbox,
        "grid": grid,
        "rhino_base": rhino_output_base(config),
        "voxel_layers": layers,
        "worldcover": {
            "selection_status": worldcover.get("selection_status"),
            "selected_path": worldcover.get("selected_path"),
            "candidate_count": worldcover.get("candidate_count"),
            "expected_tiles": expected_esa_worldcover_tiles(config),
            "candidates": worldcover.get("candidates", []),
        },
        "dem": dem,
        "osm": osm,
        "failures": failures,
        "warnings": warnings,
    }
    write_json(dirs["logs"] / "site_data_preflight.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Preflight one site before running the heavy VoxCity modeling pipeline.")
    parser.add_argument("--site-name", required=True, help="ASCII-safe site id.")
    parser.add_argument("--site-name-cn", default="", help="Human-readable site name.")
    parser.add_argument("--lat", type=float, required=True)
    parser.add_argument("--lon", type=float, required=True)
    parser.add_argument("--input-crs", default="WGS84", choices=["WGS84", "EPSG:4326", "GCJ02", "GCJ-02", "AMAP", "GAODE"])
    parser.add_argument("--half-size-m", type=float, default=250.0)
    parser.add_argument("--voxel-size-m", type=float, default=1.0)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--check-dem-remote", action="store_true", help="Probe one required DEM tile URL without writing it to cache.")
    parser.add_argument("--dem-timeout-s", type=int, default=10)
    parser.add_argument("--check-osm-remote", action="store_true", help="Probe Overpass availability with a small building/road query without writing cache.")
    parser.add_argument("--osm-timeout-s", type=int, default=10)
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when required formal data sources are missing.")
    args = parser.parse_args()

    result = preflight(args)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(1 if result["status"] == "failed" else 0)


if __name__ == "__main__":
    main()
