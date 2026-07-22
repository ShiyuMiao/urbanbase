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

from prepare_site_data_sources import prepare_site_data_sources


def make_args(site_name: str, lat: float, lon: float, strict: bool = True) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=site_name,
        site_name_cn=site_name,
        lat=lat,
        lon=lon,
        input_crs="WGS84",
        half_size_m=250.0,
        voxel_size_m=1.0,
        output_root=str(PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_prepare_tests" / site_name),
        strict=strict,
        check_dem_remote=False,
        dem_timeout_s=5,
        check_osm_remote=False,
        osm_timeout_s=5,
        extract_worldcover=False,
        fetch_dem=False,
        fetch_osm=False,
    )


def main() -> None:
    dalian = prepare_site_data_sources(make_args("prepare_dalian_dlut_west_library", 38.8831553, 121.5120457))
    beijing = prepare_site_data_sources(make_args("prepare_beijing_source_gap", 39.9042, 116.4074))
    errors: list[str] = []
    if dalian["mode"] != "check_only":
        errors.append(f"Dalian prepare test should be check_only, got {dalian['mode']}")
    if dalian["final_preflight"]["worldcover_status"] != "selected_intersecting_raster":
        errors.append(f"Dalian WorldCover should be locally covered, got {dalian['final_preflight']['worldcover_status']}")
    if dalian["final_preflight"]["dem_status"] != "cached_all":
        errors.append(f"Dalian DEM should be available from cache, got {dalian['final_preflight']['dem_status']}")
    if beijing["final_preflight"]["worldcover_status"] == "selected_intersecting_raster":
        if "ESA WorldCover coverage is missing for this AOI." in beijing["failures"]:
            errors.append(f"Beijing WorldCover is selected but missing coverage failure remains: {beijing['failures']}")
    else:
        if beijing["status"] != "failed":
            errors.append("Beijing strict prepare check should fail when WorldCover coverage is missing.")
        if "ESA WorldCover coverage is missing for this AOI." not in beijing["failures"]:
            errors.append(f"Beijing missing WorldCover failure was not reported: {beijing['failures']}")

    result: dict[str, Any] = {
        "status": "failed" if errors else "success",
        "errors": errors,
        "dalian": {
            "status": dalian["status"],
            "mode": dalian["mode"],
            "worldcover_status": dalian["final_preflight"]["worldcover_status"],
            "dem_status": dalian["final_preflight"]["dem_status"],
            "osm_status": dalian["final_preflight"]["osm_status"],
            "warnings": dalian["warnings"],
        },
        "beijing": {
            "status": beijing["status"],
            "worldcover_status": beijing["final_preflight"]["worldcover_status"],
            "failures": beijing["failures"],
        },
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
