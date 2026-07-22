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

from preflight_site_data_sources import preflight
from run_site_model import build_request

SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from china_voxel_pipeline import RunConfig, osm_shared_cache_path


def make_args(
    site_name: str,
    lat: float,
    lon: float,
    strict: bool = False,
    output_root: Path | None = None,
    half_size_m: float = 250.0,
) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=site_name,
        site_name_cn=site_name,
        lat=lat,
        lon=lon,
        input_crs="WGS84",
        half_size_m=half_size_m,
        voxel_size_m=1.0,
        output_root=str(output_root or PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_preflight_tests" / site_name),
        check_dem_remote=False,
        dem_timeout_s=5,
        check_osm_remote=False,
        osm_timeout_s=5,
        strict=strict,
    )


def config_for_args(args: argparse.Namespace) -> RunConfig:
    request = build_request(args)
    return RunConfig(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        center_lat=request.center_lat_wgs84,
        center_lon=request.center_lon_wgs84,
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        output_root=request.output_root,
    )


def write_minimal_shared_osm_cache(config: RunConfig) -> Path:
    path = osm_shared_cache_path(config)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return path
    path.write_text(
        json.dumps(
            {
                "elements": [
                    {"type": "node", "id": 1, "lat": config.center_lat - 0.0001, "lon": config.center_lon - 0.0001},
                    {"type": "node", "id": 2, "lat": config.center_lat - 0.0001, "lon": config.center_lon + 0.0001},
                    {"type": "node", "id": 3, "lat": config.center_lat + 0.0001, "lon": config.center_lon + 0.0001},
                    {"type": "node", "id": 4, "lat": config.center_lat + 0.0001, "lon": config.center_lon - 0.0001},
                    {"type": "way", "id": 10, "nodes": [1, 2, 3, 4, 1], "tags": {"building": "yes"}},
                ]
            },
            ensure_ascii=True,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def main() -> None:
    dalian = preflight(make_args("preflight_dalian_dlut_west_library", 38.8831553, 121.5120457, strict=True))
    beijing = preflight(make_args("preflight_beijing_source_gap", 39.9042, 116.4074, strict=True))
    shared_args = make_args(
        "preflight_shared_osm_cache_probe",
        38.8831553,
        121.5120457,
        strict=True,
        output_root=PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_preflight_tests" / "shared_osm_probe",
        half_size_m=123.0,
    )
    shared_config = config_for_args(shared_args)
    shared_cache = write_minimal_shared_osm_cache(shared_config)
    shared_probe = preflight(shared_args)
    errors: list[str] = []
    if dalian["status"] == "failed":
        errors.append("Dalian preflight should not fail with the local N36E120 WorldCover tile.")
    if dalian["worldcover"]["selection_status"] != "selected_intersecting_raster":
        errors.append(f"Dalian WorldCover selection is wrong: {dalian['worldcover']['selection_status']}")
    expected = "ESA_WorldCover_10m_2021_v200_N39E114_Map.tif"
    if expected not in beijing["worldcover"]["expected_tiles"]:
        errors.append(f"Beijing expected tile is missing from preflight output: {expected}")
    if beijing["worldcover"]["selection_status"] == "selected_intersecting_raster":
        if "ESA WorldCover coverage is missing for this AOI." in beijing["failures"]:
            errors.append(f"Beijing WorldCover is selected but missing coverage failure remains: {beijing['failures']}")
    elif beijing["status"] != "failed":
        errors.append("Beijing strict preflight should fail when local WorldCover coverage is missing.")
    if "status" not in dalian.get("osm", {}):
        errors.append("Dalian preflight did not report OSM cache/remote status.")
    if shared_probe["osm"]["status"] != "shared_cached_with_core_features":
        errors.append(f"Shared OSM cache was not detected: {shared_probe['osm']['status']}")

    result: dict[str, Any] = {
        "status": "failed" if errors else "success",
        "errors": errors,
        "dalian": {
            "status": dalian["status"],
            "worldcover_selection_status": dalian["worldcover"]["selection_status"],
            "dem_status": dalian["dem"]["status"],
            "osm_status": dalian["osm"]["status"],
            "grid_runtime_category": dalian["grid"]["estimated_runtime_category"],
        },
        "beijing": {
            "status": beijing["status"],
            "worldcover_selection_status": beijing["worldcover"]["selection_status"],
            "expected_tiles": beijing["worldcover"]["expected_tiles"],
            "failures": beijing["failures"],
        },
        "shared_osm_cache": {
            "path": str(shared_cache),
            "status": shared_probe["osm"]["status"],
            "counts": shared_probe["osm"]["counts"],
        },
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == "__main__":
    main()
