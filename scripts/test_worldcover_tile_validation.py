from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from plan_worldcover_tiles import ManifestSite, plan_worldcover_tiles  # noqa: E402
from validate_worldcover_tiles import validate_manifest  # noqa: E402


def assert_validation() -> dict[str, Any]:
    output_root = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_worldcover_validation_tests"
    sites = [
        ManifestSite("dalian_dlut_west_library", 38.8831553, 121.5120457, 250.0),
        ManifestSite("kunming_missing_probe", 25.0389, 102.7183, 250.0),
    ]
    dalian_tile = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "01_raw" / "ESA_WorldCover_10m_2021_v200_N36E120_Map.tif"
    expected_sizes = {
        "ESA_WorldCover_10m_2021_v200_N36E120_Map.tif": dalian_tile.stat().st_size if dalian_tile.exists() else None,
        "ESA_WorldCover_10m_2021_v200_N24E102_Map.tif": 123456,
    }
    manifest = plan_worldcover_tiles(sites, "", str(output_root), remote_size_lookup=lambda tile: expected_sizes.get(tile))
    output_json = output_root / "12_logs" / "worldcover_tile_validation.json"
    report = validate_manifest(Path(manifest["output_json"]), output_json, strict=False, tolerance=1e-6)
    strict_report = validate_manifest(Path(manifest["output_json"]), None, strict=True, tolerance=1e-6)
    errors: list[str] = []

    if report.get("status") != "completed_with_missing_tiles":
        errors.append(f"non-strict validation should report missing tiles without hard failure: {report.get('status')}")
    if report.get("valid_tile_count") != 1:
        errors.append(f"Dalian N36E120 should validate as one valid local tile: {report.get('valid_tile_count')}")
    if "ESA_WorldCover_10m_2021_v200_N24E102_Map.tif" not in report.get("missing_tiles", []):
        errors.append(f"N24E102 should be listed as missing: {report.get('missing_tiles')}")
    if strict_report.get("status") != "failed_missing_tiles":
        errors.append(f"strict validation should fail while N24E102 is missing: {strict_report.get('status')}")
    if not output_json.exists():
        errors.append(f"validation JSON was not written: {output_json}")

    valid_tiles = [tile for tile in report.get("tiles", []) if tile.get("status") == "valid"]
    if valid_tiles:
        raster = valid_tiles[0].get("raster") or {}
        if raster.get("crs") != "EPSG:4326":
            errors.append(f"valid WorldCover raster should be EPSG:4326: {raster.get('crs')}")
        if not raster.get("sample", {}).get("valid_pixel_count"):
            errors.append("valid WorldCover raster should expose non-empty sample pixels")
    else:
        errors.append("no valid WorldCover tile was found in validation report")

    return {
        "status": "success" if not errors else "failed",
        "errors": errors,
        "output_json": str(output_json),
        "validation_status": report.get("status"),
        "strict_validation_status": strict_report.get("status"),
        "valid_tile_count": report.get("valid_tile_count"),
        "missing_tile_count": report.get("missing_tile_count"),
        "missing_tiles": report.get("missing_tiles"),
    }


def main() -> None:
    result = assert_validation()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
