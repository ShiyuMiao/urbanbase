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

from real_data_readiness_report import build_readiness_report  # noqa: E402


def make_args(site_name: str, lat: float, lon: float) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=site_name,
        site_name_cn=site_name,
        lat=lat,
        lon=lon,
        input_crs="WGS84",
        half_size_m=250.0,
        voxel_size_m=1.0,
        output_root=str(PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_readiness_tests" / site_name),
        worldcover_path="",
        worldcover_bounds_tolerance_deg=1e-6,
        dem_min_bytes=1024,
        dem_max_abs_elevation_m=9000.0,
        dem_timeout_s=5,
        osm_timeout_s=5,
        allow_no_osm_core_features=False,
        strict=True,
    )


def main() -> None:
    dalian = build_readiness_report(make_args("readiness_dalian_dlut_west_library", 38.8831553, 121.5120457))
    beijing = build_readiness_report(make_args("readiness_beijing_source_gap", 39.9042, 116.4074))
    errors: list[str] = []
    if dalian.get("status") != "ready":
        errors.append(f"Dalian readiness should pass: {dalian.get('status')} {dalian.get('failed_components')}")
    if dalian.get("component_results", {}).get("worldcover") != "passed":
        errors.append(f"Dalian WorldCover component should pass: {dalian.get('worldcover')}")
    if dalian.get("component_results", {}).get("dem") != "passed":
        errors.append(f"Dalian DEM component should pass: {dalian.get('dem')}")
    if dalian.get("component_results", {}).get("osm") != "passed":
        errors.append(f"Dalian OSM component should pass: {dalian.get('osm')}")
    if beijing.get("status") != "not_ready":
        errors.append(f"Beijing readiness should remain not_ready until DEM/OSM are prepared: {beijing.get('status')}")
    beijing_worldcover = beijing.get("worldcover", {})
    if beijing_worldcover.get("status") == "success":
        if "worldcover" in beijing.get("failed_components", []):
            errors.append(f"Beijing WorldCover passed but is still listed as failed: {beijing.get('failed_components')}")
        if beijing_worldcover.get("missing_tile_count", 0) != 0:
            errors.append(f"Beijing WorldCover passed but still reports missing tiles: {beijing_worldcover}")
    else:
        if "worldcover" not in beijing.get("failed_components", []):
            errors.append(f"Beijing failed components should include WorldCover when coverage is absent: {beijing.get('failed_components')}")
        if beijing_worldcover.get("missing_tile_count", 0) <= 0:
            errors.append(f"Beijing should report missing WorldCover tiles when coverage is absent: {beijing_worldcover}")

    result: dict[str, Any] = {
        "status": "success" if not errors else "failed",
        "errors": errors,
        "dalian": {
            "status": dalian.get("status"),
            "component_results": dalian.get("component_results"),
            "worldcover": dalian.get("worldcover"),
            "dem": dalian.get("dem"),
            "osm": dalian.get("osm"),
            "report_json": dalian.get("outputs", {}).get("report_json"),
        },
        "beijing": {
            "status": beijing.get("status"),
            "failed_components": beijing.get("failed_components"),
            "worldcover": beijing.get("worldcover"),
            "report_json": beijing.get("outputs", {}).get("report_json"),
        },
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
