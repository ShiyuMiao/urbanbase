from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"{path} is not a JSON object")
    return data


def file_size_mb(path: Path) -> float:
    return round(path.stat().st_size / 1024 / 1024, 3)


def voxel_size_slug(voxel_size_m: float) -> str:
    text = f"{float(voxel_size_m):g}".replace("-", "m")
    return f"{text.replace('.', 'p')}m"


def required_layers(voxel_size_m: float) -> set[str]:
    suffix = voxel_size_slug(voxel_size_m)
    return {
        f"01_Buildings_{suffix}_Voxels",
        f"02_Roads_Hardscape_{suffix}_Voxels",
        f"03_Water_{suffix}_Voxels",
        f"04_Green_Trees_{suffix}_Voxels",
        f"05_Green_Grass_{suffix}_Voxels",
        f"06_Terrain_DEM_{suffix}_Voxels",
    }


def check_file(path: Path, label: str, errors: list[str], min_bytes: int = 1) -> None:
    if not path.exists():
        errors.append(f"missing {label}: {path}")
        return
    if path.stat().st_size < min_bytes:
        errors.append(f"{label} is empty or too small: {path}")


def verify(output_root: Path, allow_non_strict: bool = False, allow_missing_large_assets: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []

    screenshot_candidates = sorted((output_root / "10_figures").glob("*voxel_model_review.png"))
    screenshot = screenshot_candidates[0] if screenshot_candidates else output_root / "10_figures" / "MISSING_voxel_model_review.png"
    stats_path = output_root / "06_tables" / "basic_site_statistics.json"
    lcz_path = output_root / "06_tables" / "scene_classification_alcc_lcz.json"
    layer_stats_path = output_root / "06_tables" / "layer_summary_statistics.csv"
    vegetation_path = output_root / "06_tables" / "vegetation_layer_quality_summary.json"
    source_check_path = output_root / "07_audit" / "real_data_source_check.json"
    report_path = output_root / "12_logs" / "final_execution_report.json"

    stats: dict[str, Any] = {}
    lcz: dict[str, Any] = {}
    source_check: dict[str, Any] = {}
    vegetation: dict[str, Any] = {}
    if stats_path.exists():
        stats = load_json(stats_path)
    if lcz_path.exists():
        lcz = load_json(lcz_path)
    if source_check_path.exists():
        source_check = load_json(source_check_path)
    if vegetation_path.exists():
        vegetation = load_json(vegetation_path)

    features = stats.get("features", {})
    site = stats.get("site", {})
    dem = stats.get("dem", {})
    voxels = stats.get("voxels", {})
    rhino_stats = stats.get("rhino", {})
    voxel_size_m = float(site.get("voxel_size_m", 0.1) or 0.1)
    rhino = output_root / "05_rhino" / f"final_city_voxel_{voxel_size_slug(voxel_size_m)}.3dm"

    if allow_missing_large_assets and not rhino.exists():
        warnings.append("Rhino model is absent; allowed because large assets are staged separately")
    else:
        check_file(rhino, "Rhino model", errors, min_bytes=1024)
    check_file(screenshot, "review screenshot", errors, min_bytes=1024)
    for label, path in [
        ("basic statistics", stats_path),
        ("LCZ/ALCC classification", lcz_path),
        ("layer statistics", layer_stats_path),
        ("vegetation summary", vegetation_path),
        ("strict source check", source_check_path),
        ("final execution report", report_path),
    ]:
        check_file(path, label, errors)

    for key in ["building_count", "road_count"]:
        if int(features.get(key, 0) or 0) <= 0:
            errors.append(f"{key} must be positive")
    if int(features.get("green_count", 0) or 0) <= 0:
        warnings.append("green_count is zero; vegetation layer may be missing or outside AOI")
    if dem.get("status") != "success":
        errors.append(f"DEM status is not success: {dem.get('status')}")
    if float(dem.get("elevation_range_m", 0) or 0) <= 0:
        errors.append("DEM elevation_range_m must be positive so terrain relief is represented")
    if int(voxels.get("sparse_run_count", 0) or 0) <= 0:
        errors.append("sparse_run_count must be positive")
    if int(voxels.get("total_voxels_represented", 0) or 0) <= 0:
        errors.append("total_voxels_represented must be positive")
    if int(rhino_stats.get("object_count", 0) or 0) <= 0:
        errors.append("Rhino object_count must be positive")

    if source_check:
        if source_check.get("status") != "passed":
            errors.append(f"real_data_source_check status is not passed: {source_check.get('status')}")
        checks = source_check.get("checks", {})
        if not allow_non_strict and checks.get("strict_real_data") is not True:
            errors.append("strict_real_data must be true for release verification")
        for flag in ["uses_dem_fallback", "uses_worldcover_fallback", "uses_osm_empty_fallback"]:
            if checks.get(flag) is True:
                errors.append(f"{flag} is true")

    classification = lcz.get("classification", {})
    if not classification.get("lcz_primary"):
        errors.append("lcz_primary is missing")
    if not classification.get("alcc_type"):
        errors.append("alcc_type is missing")

    if vegetation:
        if vegetation.get("quality_flag") != "source_vegetation":
            warnings.append(f"vegetation quality_flag is {vegetation.get('quality_flag')}")
        veg_voxels = int(vegetation.get("vegetation_voxel_count", 0) or 0)
        if veg_voxels <= 0:
            warnings.append("vegetation_voxel_count is zero")

    present_layers: set[str] = set()
    if layer_stats_path.exists():
        with layer_stats_path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                layer = row.get("layer", "")
                present_layers.add(layer)
                voxel_count = int(float(row.get("voxel_count", 0) or 0))
                if layer in required_layers(voxel_size_m) and voxel_count <= 0:
                    errors.append(f"{layer} has zero voxel_count")
    missing_layers = required_layers(voxel_size_m) - present_layers
    if missing_layers:
        errors.append(f"missing layer statistics for: {', '.join(sorted(missing_layers))}")

    summary = {
        "status": "passed" if not errors else "failed",
        "output_root": str(output_root),
        "rhino_mb": file_size_mb(rhino) if rhino.exists() else 0,
        "screenshot_mb": file_size_mb(screenshot) if screenshot.exists() else 0,
        "site": stats.get("site", {}),
        "feature_counts": {
            "buildings": features.get("building_count"),
            "roads": features.get("road_count"),
            "water": features.get("water_count"),
            "green": features.get("green_count"),
            "poi": features.get("poi_count"),
        },
        "dem": {
            "source": dem.get("source"),
            "status": dem.get("status"),
            "elevation_range_m": dem.get("elevation_range_m"),
        },
        "voxels": {
            "sparse_run_count": voxels.get("sparse_run_count"),
            "total_voxels_represented": voxels.get("total_voxels_represented"),
        },
        "classification": classification,
        "warnings": warnings,
        "errors": errors,
    }
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify one generated VoxCity site output before release.")
    parser.add_argument("--output-root", type=Path, required=True, help="Generated site output directory.")
    parser.add_argument("--allow-non-strict", action="store_true", help="Allow non-strict preview output.")
    parser.add_argument("--allow-missing-large-assets", action="store_true", help="Allow Rhino/large model assets to be absent in source-only release staging folders.")
    args = parser.parse_args()

    summary = verify(
        args.output_root,
        allow_non_strict=args.allow_non_strict,
        allow_missing_large_assets=args.allow_missing_large_assets,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if summary["status"] != "passed":
        sys.exit(1)


if __name__ == "__main__":
    main()
