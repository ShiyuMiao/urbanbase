from __future__ import annotations

import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_dem_cache import validate_dem_caches, site_dem_cache_paths  # noqa: E402


def make_args() -> object:
    class Args:
        site_name = "dalian_dlut_west_library"
        site_name_cn = "dalian_dlut_west_library"
        lat = 38.8831553
        lon = 121.5120457
        input_crs = "WGS84"
        half_size_m = 250.0
        voxel_size_m = 1.0
        output_root = str(PROJECT_ROOT / "outputs_citylbm_voxel_china" / "dalian_dlut_west_library")

    return Args()


def main() -> None:
    output_root = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_dem_validation_tests"
    output_root.mkdir(parents=True, exist_ok=True)
    site_paths = site_dem_cache_paths(make_args())
    corrupt_tile = output_root / "13722_6268.png"
    corrupt_tile.write_bytes(b"not a png")

    valid_report = validate_dem_caches(site_paths, output_root / "valid_dem_cache_validation.json", strict=True)
    corrupt_report = validate_dem_caches([corrupt_tile], None, strict=True)
    errors: list[str] = []

    if valid_report.get("status") != "success":
        errors.append(f"Dalian DEM cache should validate successfully: {valid_report.get('status')}")
    if valid_report.get("satisfied_tile_count") != 1:
        errors.append(f"Dalian DEM should satisfy one required tile: {valid_report.get('satisfied_tile_count')}")
    if valid_report.get("valid_cache_count", 0) <= 0:
        errors.append(f"Dalian DEM should expose at least one valid cache path: {valid_report.get('valid_cache_count')}")
    elevation = valid_report.get("elevation_summary", {})
    if elevation.get("sample_elevation_range_m") is None:
        errors.append(f"Dalian DEM should include elevation summary: {elevation}")
    if corrupt_report.get("status") != "failed_invalid_tiles":
        errors.append(f"corrupt DEM cache should fail in strict mode: {corrupt_report.get('status')}")
    corrupt_errors = corrupt_report.get("tiles", [{}])[0].get("errors", [])
    if not any(str(item).startswith("png_unreadable") for item in corrupt_errors):
        errors.append(f"corrupt DEM cache should report png_unreadable: {corrupt_errors}")

    result = {
        "status": "success" if not errors else "failed",
        "errors": errors,
        "valid_status": valid_report.get("status"),
        "required_tile_count": valid_report.get("required_tile_count"),
        "satisfied_tile_count": valid_report.get("satisfied_tile_count"),
        "valid_cache_count": valid_report.get("valid_cache_count"),
        "invalid_cache_count": valid_report.get("invalid_cache_count"),
        "missing_cache_count": valid_report.get("missing_cache_count"),
        "elevation_summary": valid_report.get("elevation_summary"),
        "selected_valid_paths": valid_report.get("selected_valid_paths"),
        "corrupt_status": corrupt_report.get("status"),
        "output_json": valid_report.get("output_json"),
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
