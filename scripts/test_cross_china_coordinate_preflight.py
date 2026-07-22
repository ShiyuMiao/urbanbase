from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from china_voxel_pipeline import RunConfig, bbox_lonlat, grid_config, rhino_output_base, voxel_layer_names
from run_site_model import build_request


@dataclass(frozen=True)
class CoordinateCase:
    site_name: str
    lat: float
    lon: float
    input_crs: str
    half_size_m: float = 250.0
    voxel_size_m: float = 2.0


CASES = [
    CoordinateCase("beijing_core_wgs84", 39.9042, 116.4074, "WGS84"),
    CoordinateCase("shanghai_core_wgs84", 31.2304, 121.4737, "WGS84"),
    CoordinateCase("chengdu_core_wgs84", 30.5728, 104.0668, "WGS84"),
    CoordinateCase("shenzhen_core_wgs84", 22.5431, 114.0579, "WGS84"),
    CoordinateCase("urumqi_core_wgs84", 43.8256, 87.6168, "WGS84"),
    CoordinateCase("harbin_core_wgs84", 45.8038, 126.5349, "WGS84"),
    CoordinateCase("kunming_core_wgs84", 25.0389, 102.7183, "WGS84"),
    CoordinateCase("dalian_gcj02_input", 38.881098, 121.526615, "GCJ02"),
]


def make_args(case: CoordinateCase) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=case.site_name,
        site_name_cn=case.site_name,
        lat=case.lat,
        lon=case.lon,
        input_crs=case.input_crs,
        half_size_m=case.half_size_m,
        voxel_size_m=case.voxel_size_m,
        output_root=None,
    )


def assert_finite_bbox(case_name: str, bbox: dict[str, float]) -> None:
    for key in ["west", "south", "east", "north"]:
        value = bbox[key]
        if not math.isfinite(value):
            raise AssertionError(f"{case_name} bbox {key} is not finite: {value}")
    if not bbox["west"] < bbox["east"]:
        raise AssertionError(f"{case_name} bbox west/east order is invalid: {bbox}")
    if not bbox["south"] < bbox["north"]:
        raise AssertionError(f"{case_name} bbox south/north order is invalid: {bbox}")
    if not 73.0 <= bbox["west"] <= 136.0 or not 73.0 <= bbox["east"] <= 136.0:
        raise AssertionError(f"{case_name} bbox longitude is outside broad China bounds: {bbox}")
    if not 3.0 <= bbox["south"] <= 54.0 or not 3.0 <= bbox["north"] <= 54.0:
        raise AssertionError(f"{case_name} bbox latitude is outside broad China bounds: {bbox}")


def validate_case(case: CoordinateCase) -> dict[str, Any]:
    request = build_request(make_args(case))
    config = RunConfig(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        center_lat=request.center_lat_wgs84,
        center_lon=request.center_lon_wgs84,
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        output_root=request.output_root,
    )
    bbox = bbox_lonlat(config)
    assert_finite_bbox(case.site_name, bbox)
    grid = grid_config(config)
    if grid["nx"] <= 0 or grid["ny"] <= 0 or grid["nz"] <= 0:
        raise AssertionError(f"{case.site_name} grid dimensions are invalid: {grid}")
    if grid["tiled_output"]:
        raise AssertionError(f"{case.site_name} preflight case unexpectedly requires tiled output: {grid}")
    rhino_base = rhino_output_base(config)
    if not rhino_base.endswith("_2m"):
        raise AssertionError(f"{case.site_name} Rhino base did not preserve 2m suffix: {rhino_base}")
    layers = voxel_layer_names(config)
    for role in ["buildings", "roads", "water", "trees", "grass", "terrain"]:
        if "_2m_" not in layers[role]:
            raise AssertionError(f"{case.site_name} layer {role} lacks 2m suffix: {layers[role]}")
    return {
        "site_name": case.site_name,
        "input_crs": case.input_crs,
        "center_lat_wgs84": request.center_lat_wgs84,
        "center_lon_wgs84": request.center_lon_wgs84,
        "bbox": {key: round(float(value), 6) if isinstance(value, float) else value for key, value in bbox.items()},
        "grid": {
            "nx": grid["nx"],
            "ny": grid["ny"],
            "nz": grid["nz"],
            "runtime_category": grid["estimated_runtime_category"],
        },
        "rhino_base": rhino_base,
    }


def validate_rejections() -> dict[str, str]:
    invalid_cases = {
        "latitude_out_of_range": argparse.Namespace(site_name="bad_lat", site_name_cn="bad_lat", lat=91.0, lon=116.0, input_crs="WGS84", half_size_m=250.0, voxel_size_m=2.0, output_root=None),
        "longitude_out_of_range": argparse.Namespace(site_name="bad_lon", site_name_cn="bad_lon", lat=39.0, lon=181.0, input_crs="WGS84", half_size_m=250.0, voxel_size_m=2.0, output_root=None),
        "negative_half_size": argparse.Namespace(site_name="bad_half", site_name_cn="bad_half", lat=39.0, lon=116.0, input_crs="WGS84", half_size_m=-1.0, voxel_size_m=2.0, output_root=None),
        "zero_voxel_size": argparse.Namespace(site_name="bad_voxel", site_name_cn="bad_voxel", lat=39.0, lon=116.0, input_crs="WGS84", half_size_m=250.0, voxel_size_m=0.0, output_root=None),
        "outside_china": argparse.Namespace(site_name="paris", site_name_cn="paris", lat=48.8566, lon=2.3522, input_crs="WGS84", half_size_m=250.0, voxel_size_m=2.0, output_root=None),
    }
    result: dict[str, str] = {}
    for name, args in invalid_cases.items():
        try:
            build_request(args)
        except ValueError:
            result[name] = "rejected"
        else:
            raise AssertionError(f"{name} should have been rejected")
    return result


def main() -> None:
    cases = [validate_case(case) for case in CASES]
    result = {
        "status": "success",
        "case_count": len(cases),
        "cases": cases,
        "invalid_input_rejections": validate_rejections(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
