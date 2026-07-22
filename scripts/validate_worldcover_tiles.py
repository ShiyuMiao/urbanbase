from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from china_voxel_pipeline import OUTPUT_ROOT, rel_project_path, write_json  # noqa: E402
from plan_worldcover_tiles import tile_bounds_wgs84, tile_prefix  # noqa: E402

try:
    import rasterio
    from rasterio.warp import transform_bounds
except Exception:  # pragma: no cover - optional dependency report path
    rasterio = None
    transform_bounds = None


DEFAULT_MANIFEST = OUTPUT_ROOT / "12_logs" / "worldcover_tile_request_manifest.json"
VALID_WORLDCOVER_CLASSES = {10, 20, 30, 40, 50, 60, 70, 80, 90, 95, 100}


def load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"WorldCover tile manifest not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def project_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def default_raw_path(tile_name: str) -> Path:
    return OUTPUT_ROOT / "01_raw" / tile_name


def unique_tile_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    for site in manifest.get("sites", []):
        for tile in site.get("tiles", []):
            name = tile.get("tile_name")
            if not name:
                continue
            record = records.setdefault(
                name,
                {
                    "tile_name": name,
                    "tile_prefix": tile.get("tile_prefix") or tile_prefix(name),
                    "tile_bounds_wgs84": tile.get("tile_bounds_wgs84"),
                    "download_url": tile.get("download_url"),
                    "expected_download_bytes": tile.get("expected_download_bytes"),
                    "expected_sites": [],
                    "local_paths": [],
                },
            )
            if record.get("expected_download_bytes") is None and tile.get("expected_download_bytes") is not None:
                record["expected_download_bytes"] = tile.get("expected_download_bytes")
            if not record.get("download_url") and tile.get("download_url"):
                record["download_url"] = tile.get("download_url")
            record["expected_sites"].append(site.get("site_name"))
            for candidate in tile.get("local_paths", []):
                if candidate and candidate not in record["local_paths"]:
                    record["local_paths"].append(candidate)
    return sorted(records.values(), key=lambda item: item["tile_name"])


def bounds_contain(actual: list[float], expected: dict[str, float], tolerance: float) -> bool:
    west, south, east, north = actual
    return (
        west <= expected["west"] + tolerance
        and south <= expected["south"] + tolerance
        and east >= expected["east"] - tolerance
        and north >= expected["north"] - tolerance
    )


def raster_sample_summary(src: Any) -> dict[str, Any]:
    data = src.read(1, out_shape=(1, min(src.height, 128), min(src.width, 128)), masked=True)
    compressed = data.compressed()
    if compressed.size == 0:
        return {"valid_pixel_count": 0, "sample_values": [], "unexpected_sample_values": []}
    values = sorted({int(value) for value in compressed.tolist()})
    return {
        "valid_pixel_count": int(compressed.size),
        "sample_min": int(compressed.min()),
        "sample_max": int(compressed.max()),
        "sample_values": values[:30],
        "unexpected_sample_values": [value for value in values if value not in VALID_WORLDCOVER_CLASSES],
    }


def validate_raster(
    path: Path,
    expected_bounds: dict[str, float],
    tolerance: float,
    expected_bytes: int | None = None,
) -> dict[str, Any]:
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
    if expected_bytes is not None:
        result["expected_download_bytes"] = expected_bytes
        if result["bytes"] != expected_bytes:
            result["errors"].append("file_size_mismatch")
    if rasterio is None:
        result["status"] = "unchecked_missing_rasterio"
        result["warnings"].append("rasterio_not_available")
        return result
    try:
        with rasterio.open(path) as src:
            result["crs"] = str(src.crs) if src.crs else None
            result["width"] = int(src.width)
            result["height"] = int(src.height)
            result["bounds"] = [float(v) for v in src.bounds]
            if src.crs and transform_bounds is not None:
                bounds_wgs84 = [float(v) for v in transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)]
            else:
                bounds_wgs84 = result["bounds"]
            result["bounds_wgs84"] = bounds_wgs84
            if str(src.crs) != "EPSG:4326":
                result["errors"].append("crs_not_epsg_4326")
            if not bounds_contain(bounds_wgs84, expected_bounds, tolerance):
                result["errors"].append("bounds_do_not_cover_expected_tile")
            sample = raster_sample_summary(src)
            result["sample"] = sample
            if sample.get("valid_pixel_count", 0) <= 0:
                result["errors"].append("no_valid_sample_pixels")
            if sample.get("unexpected_sample_values"):
                result["warnings"].append("sample_contains_unexpected_worldcover_values")
    except Exception as exc:
        result["status"] = "unreadable"
        result["errors"].append(str(exc))
        return result
    result["status"] = "valid" if not result["errors"] else "invalid"
    return result


def candidate_paths(tile: dict[str, Any]) -> list[Path]:
    paths: list[Path] = []
    for value in tile.get("local_paths", []):
        if value:
            paths.append(project_path(value))
    raw_path = default_raw_path(tile["tile_name"])
    if raw_path not in paths:
        paths.append(raw_path)
    return paths


def validate_manifest(manifest_path: Path, output_json: Path | None, strict: bool, tolerance: float) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    tile_reports: list[dict[str, Any]] = []
    valid_count = 0
    missing_count = 0
    invalid_count = 0
    unchecked_count = 0

    for tile in unique_tile_records(manifest):
        prefix = tile.get("tile_prefix") or tile_prefix(tile["tile_name"])
        expected_bounds = tile.get("tile_bounds_wgs84") or tile_bounds_wgs84(prefix)
        tile_report: dict[str, Any] = {
            "tile_name": tile["tile_name"],
            "tile_prefix": prefix,
            "expected_bounds_wgs84": expected_bounds,
            "expected_sites": sorted({name for name in tile.get("expected_sites", []) if name}),
            "download_url": tile.get("download_url"),
            "expected_download_bytes": tile.get("expected_download_bytes"),
            "candidate_paths": [str(path) for path in candidate_paths(tile)],
            "status": "missing",
            "raster": None,
        }
        if not expected_bounds:
            tile_report["status"] = "invalid_manifest"
            tile_report["errors"] = ["missing_expected_tile_bounds"]
            invalid_count += 1
            tile_reports.append(tile_report)
            continue
        expected_bytes = tile.get("expected_download_bytes")
        rasters = [validate_raster(path, expected_bounds, tolerance, expected_bytes) for path in candidate_paths(tile)]
        tile_report["raster_candidates"] = rasters
        best = next((item for item in rasters if item["status"] == "valid"), None)
        if best:
            tile_report["status"] = "valid"
            tile_report["raster"] = best
            valid_count += 1
        elif any(item["status"] == "unchecked_missing_rasterio" for item in rasters):
            tile_report["status"] = "unchecked_missing_rasterio"
            tile_report["raster"] = next(item for item in rasters if item["status"] == "unchecked_missing_rasterio")
            unchecked_count += 1
        elif any(item["exists"] for item in rasters):
            tile_report["status"] = "invalid"
            tile_report["raster"] = next(item for item in rasters if item["exists"])
            invalid_count += 1
        else:
            tile_report["status"] = "missing"
            missing_count += 1
        tile_reports.append(tile_report)

    if invalid_count:
        status = "failed_invalid_tiles"
    elif strict and (missing_count or unchecked_count):
        status = "failed_missing_tiles"
    elif missing_count:
        status = "completed_with_missing_tiles"
    elif unchecked_count:
        status = "completed_unchecked_missing_rasterio"
    else:
        status = "success"

    report = {
        "status": status,
        "strict": strict,
        "manifest_path": str(manifest_path),
        "output_json": str(output_json) if output_json else None,
        "tile_count": len(tile_reports),
        "valid_tile_count": valid_count,
        "missing_tile_count": missing_count,
        "invalid_tile_count": invalid_count,
        "unchecked_tile_count": unchecked_count,
        "missing_tiles": [item["tile_name"] for item in tile_reports if item["status"] == "missing"],
        "invalid_tiles": [item["tile_name"] for item in tile_reports if item["status"] == "invalid"],
        "tiles": tile_reports,
    }
    if output_json:
        write_json(output_json, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate local ESA WorldCover GeoTIFFs referenced by the tile manifest.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_ROOT / "12_logs" / "worldcover_tile_validation.json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero if any expected tile is missing or unchecked.")
    parser.add_argument("--bounds-tolerance-deg", type=float, default=1e-6)
    args = parser.parse_args()

    result = validate_manifest(args.manifest, args.output_json, args.strict, args.bounds_tolerance_deg)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    hard_failure = result["status"].startswith("failed")
    raise SystemExit(1 if hard_failure else 0)


if __name__ == "__main__":
    main()
