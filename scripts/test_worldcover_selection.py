from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from china_voxel_pipeline import RunConfig, ensure_dirs, expected_esa_worldcover_tiles, select_esa_worldcover_raster


def probe_config(site_name: str, lat: float, lon: float) -> RunConfig:
    return RunConfig(
        site_name=site_name,
        site_name_cn=site_name,
        center_lat=lat,
        center_lon=lon,
        half_size_m=30.0,
        voxel_size_m=2.0,
        output_root=str(PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_worldcover_selection_probe" / site_name),
    )


def assert_selection() -> dict[str, Any]:
    dalian = probe_config("dalian_worldcover_selection", 38.88024056122594, 121.52153023152763)
    beijing = probe_config("beijing_worldcover_selection", 39.9042, 116.4074)
    chengdu = probe_config("chengdu_worldcover_selection", 30.5728, 104.0668)
    dalian_dirs = ensure_dirs(dalian)
    beijing_dirs = ensure_dirs(beijing)
    chengdu_dirs = ensure_dirs(chengdu)
    dalian_selection = select_esa_worldcover_raster(dalian, dalian_dirs)
    beijing_selection = select_esa_worldcover_raster(beijing, beijing_dirs)
    chengdu_selection = select_esa_worldcover_raster(chengdu, chengdu_dirs)
    dalian_expected = expected_esa_worldcover_tiles(dalian)
    beijing_expected = expected_esa_worldcover_tiles(beijing)
    chengdu_expected = expected_esa_worldcover_tiles(chengdu)

    errors: list[str] = []
    if "ESA_WorldCover_10m_2021_v200_N36E120_Map.tif" not in dalian_expected:
        errors.append(f"Dalian expected tile hint is wrong: {dalian_expected}")
    if dalian_selection.get("selection_status") != "selected_intersecting_raster":
        errors.append(f"Dalian should select the existing intersecting WorldCover raster: {dalian_selection}")
    if "ESA_WorldCover_10m_2021_v200_N39E114_Map.tif" not in beijing_expected:
        errors.append(f"Beijing expected tile hint is wrong: {beijing_expected}")
    beijing_path = beijing_selection.get("selected_path")
    if beijing_path and "N36E120" in str(beijing_path):
        errors.append(f"Beijing must not reuse the Dalian N36E120 raster: {beijing_selection}")
    if beijing_path and "N39E114" not in str(beijing_path):
        errors.append(f"Beijing should select its own N39E114 raster when available: {beijing_selection}")
    if not beijing_path and beijing_selection.get("selection_status") not in {"missing_coverage", "missing_raster"}:
        errors.append(f"Beijing missing coverage should be explicit: {beijing_selection}")
    if "ESA_WorldCover_10m_2021_v200_N30E102_Map.tif" not in chengdu_expected:
        errors.append(f"Chengdu expected tile hint is wrong: {chengdu_expected}")
    chengdu_path = chengdu_selection.get("selected_path")
    chengdu_candidates = chengdu_selection.get("candidates", [])
    chengdu_size_statuses = {
        candidate.get("size_check", {}).get("status")
        for candidate in chengdu_candidates
        if "N30E102" in str(candidate.get("path", ""))
    }
    if "file_size_mismatch" in chengdu_size_statuses:
        if chengdu_path:
            errors.append(f"Chengdu incomplete N30E102 tile must not be selected: {chengdu_selection}")
        if chengdu_selection.get("invalid_candidate_count", 0) < 1:
            errors.append(f"Chengdu incomplete N30E102 tile should be counted as invalid: {chengdu_selection}")
    elif chengdu_path and "N30E102" not in str(chengdu_path):
        errors.append(f"Chengdu should select its own N30E102 raster when available: {chengdu_selection}")
    elif not chengdu_path and chengdu_selection.get("selection_status") not in {"missing_coverage", "missing_raster"}:
        errors.append(f"Chengdu missing coverage should be explicit: {chengdu_selection}")

    return {
        "status": "success" if not errors else "failed",
        "errors": errors,
        "dalian_expected_tiles": dalian_expected,
        "dalian_selection": dalian_selection,
        "beijing_expected_tiles": beijing_expected,
        "beijing_selection": beijing_selection,
        "chengdu_expected_tiles": chengdu_expected,
        "chengdu_selection": chengdu_selection,
    }


def main() -> None:
    result = assert_selection()
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
