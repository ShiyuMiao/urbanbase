from __future__ import annotations

import argparse
import io
import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from china_voxel_pipeline import (  # noqa: E402
    OUTPUT_ROOT,
    RunConfig,
    bbox_lonlat,
    config_output_root,
    lonlat_to_webmercator_tile,
    rel_project_path,
    safe_filename,
    write_json,
)
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


def config_from_args(args: argparse.Namespace) -> RunConfig:
    request = build_request(request_namespace(args))
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


def required_dem_tiles(config: RunConfig) -> list[dict[str, Any]]:
    bbox = bbox_lonlat(config)
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


def site_dem_cache_paths(args: argparse.Namespace) -> list[Path]:
    config = config_from_args(args)
    root = config_output_root(config)
    paths: list[Path] = []
    for tile in required_dem_tiles(config):
        name = f"{tile['x']}_{tile['y']}.png"
        paths.append(root / "03_cache" / "dem_tiles" / str(tile["zoom"]) / name)
        paths.append(OUTPUT_ROOT / "03_cache" / "dem_tiles" / str(tile["zoom"]) / name)
    return paths


def terrarium_elevation(rgb: np.ndarray) -> np.ndarray:
    arr = rgb.astype(np.float32)
    return arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0 - 32768.0


def sample_summary(elevation: np.ndarray) -> dict[str, Any]:
    compressed = elevation[np.isfinite(elevation)]
    if compressed.size == 0:
        return {"valid_pixel_count": 0}
    stride_y = max(1, elevation.shape[0] // 64)
    stride_x = max(1, elevation.shape[1] // 64)
    sample = elevation[::stride_y, ::stride_x]
    sample = sample[np.isfinite(sample)]
    return {
        "valid_pixel_count": int(compressed.size),
        "sample_pixel_count": int(sample.size),
        "sample_min_elevation_m": round(float(np.min(sample)), 3),
        "sample_max_elevation_m": round(float(np.max(sample)), 3),
        "sample_mean_elevation_m": round(float(np.mean(sample)), 3),
        "sample_elevation_range_m": round(float(np.max(sample) - np.min(sample)), 3),
    }


def validate_tile(path: Path, min_bytes: int, max_abs_elevation_m: float) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "relative_path": rel_project_path(path),
        "exists": path.exists(),
        "status": "missing",
        "errors": [],
        "warnings": [],
    }
    if not path.exists():
        result["errors"].append("file_missing")
        return result
    result["bytes"] = path.stat().st_size
    if result["bytes"] < min_bytes:
        result["errors"].append("file_too_small")
    try:
        image = Image.open(io.BytesIO(path.read_bytes())).convert("RGB")
        rgb = np.asarray(image, dtype=np.uint8)
    except Exception as exc:
        result["status"] = "unreadable"
        result["errors"].append(f"png_unreadable:{exc}")
        return result
    result["width"] = int(image.width)
    result["height"] = int(image.height)
    result["mode"] = image.mode
    if image.width != 256 or image.height != 256:
        result["warnings"].append("unexpected_tile_dimensions")
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        result["errors"].append("missing_rgb_channels")
        result["status"] = "invalid"
        return result

    elevation = terrarium_elevation(rgb)
    summary = sample_summary(elevation)
    result["elevation"] = summary
    if summary.get("valid_pixel_count", 0) <= 0:
        result["errors"].append("no_valid_elevation_pixels")
    min_z = summary.get("sample_min_elevation_m")
    max_z = summary.get("sample_max_elevation_m")
    if isinstance(min_z, (int, float)) and isinstance(max_z, (int, float)):
        if abs(min_z) > max_abs_elevation_m or abs(max_z) > max_abs_elevation_m:
            result["errors"].append("elevation_out_of_reasonable_bounds")
    if summary.get("sample_elevation_range_m") == 0:
        result["warnings"].append("flat_sample_elevation")
    result["status"] = "valid" if not result["errors"] else "invalid"
    return result


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def group_required_tiles(paths: list[Path]) -> dict[str, list[Path]]:
    groups: dict[str, list[Path]] = {}
    for path in paths:
        groups.setdefault(path.name, []).append(path)
    return groups


def validate_dem_caches(
    cache_paths: list[Path],
    output_json: Path | None,
    strict: bool,
    min_bytes: int = 1024,
    max_abs_elevation_m: float = 9000.0,
) -> dict[str, Any]:
    paths = unique_paths(cache_paths)
    reports = [validate_tile(path, min_bytes, max_abs_elevation_m) for path in paths]
    by_path = {item["path"]: item for item in reports}
    groups = group_required_tiles(paths)
    satisfied_tiles = 0
    missing_tile_names: list[str] = []
    invalid_tile_names: list[str] = []
    for tile_name, group_paths in groups.items():
        group_reports = [by_path[str(path)] for path in group_paths]
        if any(item["status"] == "valid" for item in group_reports):
            satisfied_tiles += 1
        elif any(item["status"] in {"invalid", "unreadable"} for item in group_reports):
            invalid_tile_names.append(tile_name)
        else:
            missing_tile_names.append(tile_name)
    valid = [item for item in reports if item["status"] == "valid"]
    invalid = [item for item in reports if item["status"] in {"invalid", "unreadable"}]
    missing = [item for item in reports if item["status"] == "missing"]
    if invalid_tile_names:
        status = "failed_invalid_tiles"
    elif strict and missing_tile_names:
        status = "failed_missing_tiles"
    elif missing_tile_names:
        status = "completed_with_missing_tiles"
    else:
        status = "success"
    elevations = [item.get("elevation", {}) for item in valid]
    min_values = [item["sample_min_elevation_m"] for item in elevations if "sample_min_elevation_m" in item]
    max_values = [item["sample_max_elevation_m"] for item in elevations if "sample_max_elevation_m" in item]
    report = {
        "status": status,
        "strict": strict,
        "output_json": str(output_json) if output_json else None,
        "cache_path_count": len(reports),
        "required_tile_count": len(groups),
        "satisfied_tile_count": satisfied_tiles,
        "valid_cache_count": len(valid),
        "invalid_cache_count": len(invalid),
        "missing_cache_count": len(missing),
        "missing_tiles": sorted(set(missing_tile_names)),
        "invalid_tiles": sorted(set(invalid_tile_names)),
        "selected_valid_paths": [item["path"] for item in valid],
        "elevation_summary": {
            "min_sample_elevation_m": round(float(min(min_values)), 3) if min_values else None,
            "max_sample_elevation_m": round(float(max(max_values)), 3) if max_values else None,
            "sample_elevation_range_m": round(float(max(max_values) - min(min_values)), 3) if min_values and max_values else None,
        },
        "tiles": reports,
    }
    if output_json:
        write_json(output_json, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate cached Terrarium DEM PNG tiles before formal VoxCity modeling.")
    parser.add_argument("--cache-path", action="append", type=Path, default=[], help="Explicit DEM cache PNG to validate. Can be repeated.")
    parser.add_argument("--site-name", help="ASCII-safe site id. Used with lat/lon to derive site and shared DEM tile paths.")
    parser.add_argument("--site-name-cn", default="", help="Human-readable site name.")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--input-crs", default="WGS84", choices=["WGS84", "EPSG:4326", "GCJ02", "GCJ-02", "AMAP", "GAODE"])
    parser.add_argument("--half-size-m", type=float, default=250.0)
    parser.add_argument("--voxel-size-m", type=float, default=1.0)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_ROOT / "12_logs" / "dem_cache_validation.json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless every required tile has at least one valid cache.")
    parser.add_argument("--min-bytes", type=int, default=1024)
    parser.add_argument("--max-abs-elevation-m", type=float, default=9000.0)
    args = parser.parse_args()

    cache_paths = list(args.cache_path)
    if args.site_name:
        if args.lat is None or args.lon is None:
            parser.error("--lat and --lon are required with --site-name")
        cache_paths.extend(site_dem_cache_paths(args))
    if not cache_paths:
        parser.error("provide --cache-path or --site-name with --lat/--lon")

    result = validate_dem_caches(cache_paths, args.output_json, args.strict, args.min_bytes, args.max_abs_elevation_m)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(1 if result["status"].startswith("failed") else 0)


if __name__ == "__main__":
    main()
