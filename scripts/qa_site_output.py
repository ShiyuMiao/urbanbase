from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


REQUIRED_FILES = {
    "origin_mapping": "02_gis/origin_mapping.json",
    "voxel_grid_config": "04_voxels/voxel_grid_config.json",
    "voxel_table": "04_voxels/sparse_voxels.csv",
    "site_statistics": "06_tables/basic_site_statistics.csv",
    "quality_report": "07_audit/morphology_lcz_risk_quality_report.json",
    "morphology": "08_morphology/morphology_indicators_250m.csv",
    "lcz": "09_lcz/lcz_classification_250m.csv",
    "risk": "14_heat_wind_risk/heat_wind_compound_risk_250m.csv",
    "typical_blocks": "15_typical_blocks/typical_blocks_for_citylbm.csv",
    "run_report": "12_logs/run_report.json",
}

OPTIONAL_FILES = {
    "site_summary": "12_logs/site_model_summary.json",
    "real_data_source_check": "07_audit/real_data_source_check.json",
}

MORPHOLOGY_REQUIRED_COLUMNS = {
    "basic": {
        "grid_id",
        "row",
        "col",
        "grid_size_m",
        "area_m2",
        "center_lon",
        "center_lat",
        "data_source_buildings",
        "data_source_green",
        "data_source_terrain",
        "source_quality_flag",
    },
    "building_morphology": {
        "building_count",
        "building_footprint_area_m2",
        "building_coverage_ratio",
        "building_height_mean_m",
        "building_height_max_m",
        "building_floor_area_est_m2",
        "floor_area_ratio_est",
        "building_height_std_m",
    },
    "spatial_openness": {
        "open_space_ratio",
        "road_centerline_length_m",
        "road_surface_area_est_m2",
        "impervious_surface_ratio",
        "unbuilt_pervious_proxy_ratio",
    },
    "ventilation_morphology": {
        "frontal_area_index_north_proxy",
        "frontal_area_index_east_proxy",
        "frontal_area_index_mean_proxy",
        "height_to_road_width_proxy",
        "ventilation_open_corridor_proxy",
    },
    "blue_green_space": {
        "green_area_m2",
        "green_ratio",
        "tree_cover_area_m2",
        "tree_cover_ratio",
        "grass_area_m2",
        "grass_ratio",
        "water_area_m2",
        "water_ratio",
        "blue_green_ratio",
    },
    "terrain": {
        "terrain_elevation_mean_m",
        "terrain_elevation_min_m",
        "terrain_elevation_max_m",
        "terrain_relief_m",
        "terrain_elevation_std_m",
        "terrain_slope_proxy",
    },
}
LCZ_REQUIRED_COLUMNS = {
    "lcz_rule",
    "lcz_rule_confidence",
    "lcz_rule_reasons",
    "lcz_probability_top1",
    "lcz_probability_top2",
    "lcz_top1_probability",
    "lcz_top2_probability",
    "lcz_top1_top2_margin",
    "lcz_entropy",
    "lcz_entropy_norm",
    "lcz_confidence_level",
    "lcz_distance_top1",
}
RISK_REQUIRED_COLUMNS = {
    "heat_risk_score",
    "heat_risk_level",
    "low_ventilation_risk_score",
    "low_ventilation_risk_level",
    "exposure_score",
    "exposure_level",
    "heat_wind_compound_risk_score",
    "heat_wind_compound_risk_level",
    "risk_data_sources",
    "risk_quality_flags",
}
TYPICAL_BLOCK_REQUIRED_COLUMNS = {"selection_score", "risk_rank"}
RATIO_COLUMNS = {
    "building_coverage_ratio",
    "open_space_ratio",
    "impervious_surface_ratio",
    "unbuilt_pervious_proxy_ratio",
    "ventilation_open_corridor_proxy",
    "green_ratio",
    "tree_cover_ratio",
    "grass_ratio",
    "water_ratio",
    "blue_green_ratio",
}
PROBABILITY_COLUMNS = {
    "lcz_rule_confidence",
    "lcz_top1_probability",
    "lcz_top2_probability",
    "lcz_top1_top2_margin",
    "lcz_entropy_norm",
}
RISK_SCORE_COLUMNS = {
    "heat_risk_score",
    "low_ventilation_risk_score",
    "exposure_score",
    "heat_wind_compound_risk_score",
}
NONNEGATIVE_COLUMNS = {
    "row",
    "col",
    "grid_size_m",
    "area_m2",
    "building_count",
    "building_footprint_area_m2",
    "building_height_mean_m",
    "building_height_max_m",
    "building_floor_area_est_m2",
    "floor_area_ratio_est",
    "building_height_std_m",
    "road_centerline_length_m",
    "road_surface_area_est_m2",
    "frontal_area_index_north_proxy",
    "frontal_area_index_east_proxy",
    "frontal_area_index_mean_proxy",
    "height_to_road_width_proxy",
    "green_area_m2",
    "tree_cover_area_m2",
    "grass_area_m2",
    "water_area_m2",
    "terrain_relief_m",
    "terrain_elevation_std_m",
    "terrain_slope_proxy",
    "lcz_entropy",
    "lcz_distance_top1",
    "risk_rank",
}
FINITE_NUMERIC_COLUMNS = {"selection_score"}
LCZ_CONFIDENCE_LEVELS = {"low", "medium", "high"}
RISK_LEVELS = {"low", "medium", "high", "very_high"}


def _voxel_size_slug(voxel_size_m: float) -> str:
    text = f"{float(voxel_size_m):g}".replace("-", "m")
    return f"{text.replace('.', 'p')}m"


def _rhino_bases(output_root: Path) -> list[str]:
    bases: list[str] = []
    voxel_config = output_root / REQUIRED_FILES["voxel_grid_config"]
    if voxel_config.exists():
        try:
            config = json.loads(voxel_config.read_text(encoding="utf-8"))
            bases.append(f"final_city_voxel_{_voxel_size_slug(float(config['voxel_size_m']))}")
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            pass
    for metadata in sorted((output_root / "05_rhino").glob("final_city_voxel_*_metadata.json")):
        bases.append(metadata.name.removesuffix("_metadata.json"))
    bases.append("final_city_voxel_0p1m")
    deduped: list[str] = []
    for base in bases:
        if base not in deduped:
            deduped.append(base)
    return deduped


def _first_existing_or_default(paths: list[Path]) -> Path:
    for path in paths:
        if path.exists():
            return path
    return paths[0]


def _metadata_rhino_path(output_root: Path, metadata_path: Path) -> Path | None:
    if not metadata_path.exists():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    file_value = metadata.get("file")
    if not file_value:
        return None
    raw_path = Path(str(file_value))
    if raw_path.is_absolute():
        return raw_path
    candidates = [
        output_root / raw_path,
        output_root / "05_rhino" / raw_path.name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[-1]


def _file_check(output_root: Path) -> dict[str, Any]:
    checks: dict[str, Any] = {}
    for key, rel in REQUIRED_FILES.items():
        path = output_root / rel
        checks[key] = {"path": str(path), "exists": path.exists(), "bytes": path.stat().st_size if path.exists() else 0}
    rhino_bases = _rhino_bases(output_root)
    rhino_metadata_path = _first_existing_or_default([output_root / "05_rhino" / f"{base}_metadata.json" for base in rhino_bases])
    rhino_path = _metadata_rhino_path(output_root, rhino_metadata_path)
    if rhino_path is None:
        rhino_path = _first_existing_or_default([output_root / "05_rhino" / f"{base}.3dm" for base in rhino_bases])
    rhino_layers_path = _first_existing_or_default([output_root / "05_rhino" / f"{base}_layers.csv" for base in rhino_bases])
    checks["rhino"] = {"path": str(rhino_path), "exists": rhino_path.exists(), "bytes": rhino_path.stat().st_size if rhino_path.exists() else 0}
    checks["rhino_metadata"] = {
        "path": str(rhino_metadata_path),
        "exists": rhino_metadata_path.exists(),
        "bytes": rhino_metadata_path.stat().st_size if rhino_metadata_path.exists() else 0,
    }
    checks["rhino_layers"] = {
        "path": str(rhino_layers_path),
        "exists": rhino_layers_path.exists(),
        "bytes": rhino_layers_path.stat().st_size if rhino_layers_path.exists() else 0,
    }
    for key, rel in OPTIONAL_FILES.items():
        path = output_root / rel
        checks[key] = {
            "path": str(path),
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
            "optional": True,
        }
    figures = sorted((output_root / "10_figures").glob("*voxel_model_review.png"))
    checks["preview_image"] = {
        "path": str(figures[-1]) if figures else "",
        "exists": bool(figures),
        "bytes": figures[-1].stat().st_size if figures else 0,
    }
    return checks


def _checked_path(file_checks: dict[str, Any], key: str) -> Path:
    return Path(file_checks[key]["path"])


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _stat_map(path: Path) -> dict[tuple[str, str], Any]:
    stats = pd.read_csv(path)
    return {(row["category"], row["metric"]): row["value"] for _, row in stats.iterrows()}


def _positive_layer_count(layer_counts: dict[str, Any], token: str) -> int:
    total = 0
    for layer, count in layer_counts.items():
        if token in str(layer):
            total += _as_int(count)
    return total


def _layer_table_names(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        table = pd.read_csv(path)
    except Exception:
        return []
    if "layer" not in table.columns:
        return []
    return [str(item) for item in table["layer"].dropna().tolist()]


def _read_rhino_file_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "readable": False,
        "object_count": None,
        "layer_count": None,
        "layer_names": [],
        "error": None,
    }
    try:
        import rhino3dm
    except Exception as exc:
        summary["error"] = f"rhino3dm import failed: {exc}"
        return summary
    try:
        model = rhino3dm.File3dm.Read(str(path))
    except Exception as exc:
        summary["error"] = f"Rhino read failed: {exc}"
        return summary
    if model is None:
        summary["error"] = "Rhino read returned None"
        return summary
    layer_names = [str(model.Layers[i].Name) for i in range(len(model.Layers))]
    summary.update(
        {
            "readable": True,
            "object_count": len(model.Objects),
            "layer_count": len(model.Layers),
            "layer_names": layer_names,
        }
    )
    return summary


def _read_image_summary(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "readable": False,
        "format": None,
        "width": None,
        "height": None,
        "error": None,
    }
    try:
        from PIL import Image
    except Exception as exc:
        summary["error"] = f"Pillow import failed: {exc}"
        return summary
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            summary.update(
                {
                    "readable": True,
                    "format": image.format,
                    "width": int(width),
                    "height": int(height),
                }
            )
    except Exception as exc:
        summary["error"] = f"Image read failed: {exc}"
    return summary


def _flatten_column_groups(groups: dict[str, set[str]]) -> set[str]:
    required: set[str] = set()
    for columns in groups.values():
        required.update(columns)
    return required


def _table_schema_check(path: Path, required_columns: set[str]) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "row_count": None,
        "column_count": None,
        "missing_columns": sorted(required_columns),
        "null_columns": [],
        "status": "missing",
    }
    if not path.exists():
        return summary
    try:
        table = pd.read_csv(path)
    except Exception as exc:
        summary["status"] = "unreadable"
        summary["error"] = str(exc)
        return summary
    columns = set(str(column) for column in table.columns)
    missing_columns = sorted(required_columns - columns)
    present_required = sorted(required_columns & columns)
    null_columns = [column for column in present_required if table[column].isna().any()]
    summary.update(
        {
            "row_count": int(len(table)),
            "column_count": int(len(table.columns)),
            "missing_columns": missing_columns,
            "null_columns": null_columns,
            "status": "passed" if not missing_columns and not null_columns and len(table) > 0 else "failed",
        }
    )
    return summary


def _numeric_column(table: pd.DataFrame, column: str, errors: list[str]) -> pd.Series | None:
    if column not in table.columns:
        return None
    values = pd.to_numeric(table[column], errors="coerce")
    invalid_count = int(values.isna().sum())
    if invalid_count:
        errors.append(f"{column} has {invalid_count} non-numeric or missing values")
    finite_count = int(np.isfinite(values).sum())
    if finite_count != len(values):
        errors.append(f"{column} has {len(values) - finite_count} non-finite values")
    return values


def _check_numeric_finite(table: pd.DataFrame, columns: set[str], errors: list[str]) -> list[str]:
    checked: list[str] = []
    for column in sorted(columns & set(table.columns)):
        _numeric_column(table, column, errors)
        checked.append(column)
    return checked


def _check_numeric_range(table: pd.DataFrame, columns: set[str], lo: float, hi: float, errors: list[str]) -> list[str]:
    checked: list[str] = []
    for column in sorted(columns & set(table.columns)):
        values = _numeric_column(table, column, errors)
        if values is None:
            continue
        checked.append(column)
        bad_count = int(((values < lo) | (values > hi)).sum())
        if bad_count:
            errors.append(f"{column} has {bad_count} values outside [{lo}, {hi}]")
    return checked


def _check_allowed_strings(table: pd.DataFrame, column: str, allowed: set[str], errors: list[str]) -> None:
    if column not in table.columns:
        return
    observed = set(str(value) for value in table[column].dropna().unique())
    invalid = sorted(observed - allowed)
    if invalid:
        errors.append(f"{column} has unsupported values: {invalid}")


def _table_value_check(path: Path) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "path": str(path),
        "status": "missing",
        "errors": [],
        "checked_range_columns": [],
    }
    if not path.exists():
        return summary
    try:
        table = pd.read_csv(path)
    except Exception as exc:
        summary["status"] = "unreadable"
        summary["errors"] = [str(exc)]
        return summary

    errors: list[str] = []
    checked_columns: list[str] = []
    checked_columns.extend(_check_numeric_range(table, RATIO_COLUMNS, 0.0, 1.0, errors))
    checked_columns.extend(_check_numeric_range(table, PROBABILITY_COLUMNS, 0.0, 1.0, errors))
    checked_columns.extend(_check_numeric_range(table, RISK_SCORE_COLUMNS, 0.0, 1.0, errors))
    checked_columns.extend(_check_numeric_range(table, NONNEGATIVE_COLUMNS, 0.0, float("inf"), errors))
    checked_columns.extend(_check_numeric_finite(table, FINITE_NUMERIC_COLUMNS, errors))
    checked_columns.extend(_check_numeric_range(table, {"center_lon"}, -180.0, 180.0, errors))
    checked_columns.extend(_check_numeric_range(table, {"center_lat"}, -90.0, 90.0, errors))
    _check_allowed_strings(table, "lcz_confidence_level", LCZ_CONFIDENCE_LEVELS, errors)
    for column in ["heat_risk_level", "low_ventilation_risk_level", "exposure_level", "heat_wind_compound_risk_level"]:
        _check_allowed_strings(table, column, RISK_LEVELS, errors)

    if {"lcz_top1_probability", "lcz_top2_probability"}.issubset(table.columns):
        top1 = _numeric_column(table, "lcz_top1_probability", errors)
        top2 = _numeric_column(table, "lcz_top2_probability", errors)
        if top1 is not None and top2 is not None:
            bad_count = int((top1 + 1e-9 < top2).sum())
            if bad_count:
                errors.append(f"lcz_top1_probability is below lcz_top2_probability in {bad_count} rows")
    if {"terrain_elevation_min_m", "terrain_elevation_mean_m", "terrain_elevation_max_m"}.issubset(table.columns):
        terrain_min = _numeric_column(table, "terrain_elevation_min_m", errors)
        terrain_mean = _numeric_column(table, "terrain_elevation_mean_m", errors)
        terrain_max = _numeric_column(table, "terrain_elevation_max_m", errors)
        if terrain_min is not None and terrain_mean is not None and terrain_max is not None:
            bad_count = int(((terrain_min > terrain_mean + 1e-9) | (terrain_mean > terrain_max + 1e-9)).sum())
            if bad_count:
                errors.append(f"terrain elevation min/mean/max ordering is invalid in {bad_count} rows")

    summary.update(
        {
            "status": "passed" if not errors else "failed",
            "errors": errors,
            "checked_range_columns": sorted(set(checked_columns)),
        }
    )
    return summary


def _check_close(
    label: str,
    observed: Any,
    expected: float | None,
    tolerance: float,
    errors: list[str],
) -> None:
    if expected is None:
        return
    observed_f = _as_float(observed, default=float("nan"))
    if pd.isna(observed_f) or abs(observed_f - expected) > tolerance:
        errors.append(f"{label} {observed!r} differs from expected {expected} by more than {tolerance}")


def qa_site_output(
    output_root: str | Path,
    min_buildings: int = 1,
    min_green_features: int = 0,
    min_dem_relief_m: float = 0.0,
    expected_lat: float | None = None,
    expected_lon: float | None = None,
    expected_aoi_width_m: float | None = None,
    expected_voxel_size_m: float | None = None,
    required_layer_tokens: list[str] | None = None,
    require_real_data_sources: bool = False,
    require_readiness_check: bool = False,
    require_preview_image: bool = True,
    coordinate_tolerance_deg: float = 1e-5,
    metric_tolerance_m: float = 1e-6,
) -> dict[str, Any]:
    output_root = Path(output_root)
    file_checks = _file_check(output_root)
    errors: list[str] = []
    warnings: list[str] = []
    optional_missing: list[str] = []
    for key, check in file_checks.items():
        if key == "preview_image" and not require_preview_image:
            continue
        if check.get("optional") and not check["exists"]:
            optional_missing.append(f"{key} -> {check['path']}")
            continue
        if not check["exists"]:
            errors.append(f"Missing required artifact: {key} -> {check['path']}")
        elif check["bytes"] <= 0:
            errors.append(f"Empty artifact: {key} -> {check['path']}")

    rhino_meta: dict[str, Any] = {}
    quality: dict[str, Any] = {}
    origin_mapping: dict[str, Any] = {}
    voxel_grid: dict[str, Any] = {}
    run_report: dict[str, Any] = {}
    feature_counts: dict[str, int] = {}
    dem_elevation_range_m: float | None = None
    semantic_layer_summary: dict[str, Any] = {}
    real_data_summary: dict[str, Any] = {}
    site_summary: dict[str, Any] = {}
    rhino_file_summary: dict[str, Any] = {}
    preview_image_summary: dict[str, Any] = {}
    table_schema_summary: dict[str, Any] = {}
    table_value_summary: dict[str, Any] = {}
    preview_image_path = _checked_path(file_checks, "preview_image")
    if require_preview_image and preview_image_path.exists():
        preview_image_summary = _read_image_summary(preview_image_path)
        if not preview_image_summary.get("readable"):
            errors.append(f"Preview image is not readable by Pillow: {preview_image_summary.get('error')}")
        elif _as_int(preview_image_summary.get("width")) <= 0 or _as_int(preview_image_summary.get("height")) <= 0:
            errors.append(f"Preview image has invalid dimensions: {preview_image_summary}")
    if (output_root / REQUIRED_FILES["origin_mapping"]).exists():
        origin_mapping = _read_json(output_root / REQUIRED_FILES["origin_mapping"])
        if origin_mapping.get("unit") != "meter":
            errors.append(f"origin_mapping unit is not meter: {origin_mapping.get('unit')}")
        _check_close("origin_lat", origin_mapping.get("origin_lat"), expected_lat, coordinate_tolerance_deg, errors)
        _check_close("origin_lon", origin_mapping.get("origin_lon"), expected_lon, coordinate_tolerance_deg, errors)
    if (output_root / REQUIRED_FILES["voxel_grid_config"]).exists():
        voxel_grid = _read_json(output_root / REQUIRED_FILES["voxel_grid_config"])
        if _as_float(voxel_grid.get("voxel_size_m")) <= 0:
            errors.append("voxel_grid_config voxel_size_m is missing or non-positive")
        if _as_float(voxel_grid.get("aoi_width_m")) <= 0 or _as_float(voxel_grid.get("aoi_height_m")) <= 0:
            errors.append("voxel_grid_config AOI width/height is missing or non-positive")
        _check_close("aoi_width_m", voxel_grid.get("aoi_width_m"), expected_aoi_width_m, metric_tolerance_m, errors)
        _check_close("aoi_height_m", voxel_grid.get("aoi_height_m"), expected_aoi_width_m, metric_tolerance_m, errors)
        _check_close("voxel_size_m", voxel_grid.get("voxel_size_m"), expected_voxel_size_m, metric_tolerance_m, errors)
    if (output_root / REQUIRED_FILES["run_report"]).exists():
        run_report = _read_json(output_root / REQUIRED_FILES["run_report"])
        config = run_report.get("config", {})
        if origin_mapping:
            _check_close("run_report center_lat", config.get("center_lat"), _as_float(origin_mapping.get("origin_lat")), coordinate_tolerance_deg, errors)
            _check_close("run_report center_lon", config.get("center_lon"), _as_float(origin_mapping.get("origin_lon")), coordinate_tolerance_deg, errors)
        if voxel_grid:
            _check_close("run_report voxel_size_m", config.get("voxel_size_m"), _as_float(voxel_grid.get("voxel_size_m")), metric_tolerance_m, errors)
            _check_close("run_report AOI width", _as_float(config.get("half_size_m")) * 2.0, _as_float(voxel_grid.get("aoi_width_m")), metric_tolerance_m, errors)

    rhino_metadata_path = _checked_path(file_checks, "rhino_metadata")
    rhino_path = _checked_path(file_checks, "rhino")
    if rhino_path.exists():
        rhino_file_summary = _read_rhino_file_summary(rhino_path)
        if not rhino_file_summary.get("readable"):
            errors.append(f"Rhino file is not readable by rhino3dm: {rhino_file_summary.get('error')}")
        elif _as_int(rhino_file_summary.get("object_count")) <= 0:
            errors.append("Rhino file contains zero objects")
    if rhino_metadata_path.exists():
        rhino_meta = _read_json(rhino_metadata_path)
        if int(rhino_meta.get("layer_count", 0)) < 6:
            errors.append("Rhino layer_count is unexpectedly low")
        if int(rhino_meta.get("object_count", 0)) <= 0:
            errors.append("Rhino object_count is zero")
        if int(rhino_meta.get("total_voxels_represented", 0)) <= 0:
            errors.append("Rhino metadata reports zero represented voxels")
        rhino_file = rhino_meta.get("file")
        if rhino_file:
            rhino_file_path = _metadata_rhino_path(output_root, rhino_metadata_path)
            if not rhino_file_path or not rhino_file_path.exists():
                errors.append(f"Rhino metadata file target is missing: {rhino_file}")
        if voxel_grid:
            _check_close("Rhino metadata voxel_size_m", rhino_meta.get("voxel_size_m"), _as_float(voxel_grid.get("voxel_size_m")), metric_tolerance_m, errors)
        if rhino_file_summary.get("readable"):
            if _as_int(rhino_file_summary.get("object_count")) != _as_int(rhino_meta.get("object_count")):
                errors.append(
                    "Rhino readable object_count "
                    f"{rhino_file_summary.get('object_count')} differs from metadata {rhino_meta.get('object_count')}"
                )
            if _as_int(rhino_file_summary.get("layer_count")) != _as_int(rhino_meta.get("layer_count")):
                errors.append(
                    "Rhino readable layer_count "
                    f"{rhino_file_summary.get('layer_count')} differs from metadata {rhino_meta.get('layer_count')}"
                )
    rhino_layers_path = _checked_path(file_checks, "rhino_layers")
    layer_table_names = _layer_table_names(rhino_layers_path)
    layer_voxel_counts = rhino_meta.get("layer_voxel_counts", {}) if isinstance(rhino_meta.get("layer_voxel_counts", {}), dict) else {}
    required_layer_tokens = required_layer_tokens or []
    missing_required_layers: list[str] = []
    required_layer_voxels: dict[str, int] = {}
    for token in required_layer_tokens:
        voxel_count = _positive_layer_count(layer_voxel_counts, token)
        required_layer_voxels[token] = voxel_count
        if voxel_count <= 0:
            missing_required_layers.append(token)
    if missing_required_layers:
        errors.append(f"Required semantic voxel layers are missing or empty: {missing_required_layers}")
    if required_layer_tokens and not layer_table_names:
        errors.append(f"Rhino layer color table is missing or unreadable: {rhino_layers_path}")
    for token in required_layer_tokens:
        if layer_table_names and not any(token in layer for layer in layer_table_names):
            errors.append(f"Rhino layer color table does not contain required token: {token}")
        if rhino_file_summary.get("readable") and not any(token in layer for layer in rhino_file_summary.get("layer_names", [])):
            errors.append(f"Rhino file does not contain required layer token: {token}")
    if (output_root / REQUIRED_FILES["quality_report"]).exists():
        quality = _read_json(output_root / REQUIRED_FILES["quality_report"])
        if quality.get("status") != "passed":
            errors.append(f"Morphology/LCZ/risk quality report is not passed: {quality.get('hard_errors')}")

    if (output_root / REQUIRED_FILES["site_statistics"]).exists():
        stat_map = _stat_map(output_root / REQUIRED_FILES["site_statistics"])
        building_count = _as_int(stat_map.get(("features", "building_count"), 0))
        green_count = _as_int(stat_map.get(("features", "green_count"), 0))
        feature_counts = {
            "building_count": building_count,
            "road_count": _as_int(stat_map.get(("features", "road_count"), 0)),
            "water_count": _as_int(stat_map.get(("features", "water_count"), 0)),
            "green_count": green_count,
            "poi_count": _as_int(stat_map.get(("features", "poi_count"), 0)),
        }
        if building_count < min_buildings:
            errors.append(f"building_count {building_count} is below minimum {min_buildings}")
        if green_count < min_green_features:
            errors.append(f"green_count {green_count} is below minimum {min_green_features}")
        dem_elevation_range_m = _as_float(stat_map.get(("dem", "elevation_range_m"), 0.0))
        if dem_elevation_range_m < min_dem_relief_m:
            errors.append(f"DEM elevation range {dem_elevation_range_m} m is below minimum {min_dem_relief_m} m")
        elif dem_elevation_range_m <= 0:
            warnings.append("DEM elevation range is zero or missing")
    real_data_path = output_root / OPTIONAL_FILES["real_data_source_check"]
    if real_data_path.exists():
        real_data_summary = _read_json(real_data_path)
        checks = real_data_summary.get("checks", {})
        if require_real_data_sources:
            if real_data_summary.get("status") != "passed":
                errors.append(f"Real data source check is not passed: {real_data_summary.get('failures')}")
            for key in ["uses_dem_fallback", "uses_worldcover_fallback", "uses_osm_empty_fallback"]:
                if checks.get(key):
                    errors.append(f"Real data source check reports fallback use: {key}")
            if checks.get("dem_status") != "success":
                errors.append(f"DEM source status is not success: {checks.get('dem_status')}")
            if checks.get("worldcover_status") != "success":
                errors.append(f"WorldCover source status is not success: {checks.get('worldcover_status')}")
    elif require_real_data_sources:
        errors.append(f"Missing real data source audit: {real_data_path}")

    site_summary_path = output_root / OPTIONAL_FILES["site_summary"]
    if site_summary_path.exists():
        site_summary = _read_json(site_summary_path)
    if require_readiness_check:
        if not site_summary:
            errors.append(f"Missing site model summary for readiness QA: {site_summary_path}")
        readiness = site_summary.get("readiness_check", {}) if site_summary else {}
        if readiness.get("enabled") is not True:
            errors.append("Readiness check was not enabled for this formal output")
        if readiness.get("status") != "ready":
            errors.append(f"Readiness check status is not ready: {readiness.get('status')}")
        component_results = readiness.get("component_results", {})
        for key in ["preflight", "worldcover", "dem", "osm"]:
            if component_results.get(key) != "passed":
                errors.append(f"Readiness component {key} is not passed: {component_results.get(key)}")
        if not readiness.get("report_json"):
            errors.append("Readiness report_json is missing from site model summary")

    table_rows: dict[str, int] = {}
    for key in ["morphology", "lcz", "risk", "typical_blocks"]:
        path = output_root / REQUIRED_FILES[key]
        if path.exists():
            table_rows[key] = len(pd.read_csv(path))
    if len({table_rows.get("morphology"), table_rows.get("lcz"), table_rows.get("risk")}) > 1:
        errors.append(f"morphology, LCZ, and risk row counts differ: {table_rows}")
    if table_rows.get("typical_blocks", 0) <= 0:
        errors.append("No typical blocks exported")
    table_schema_summary = {
        "morphology": _table_schema_check(output_root / REQUIRED_FILES["morphology"], _flatten_column_groups(MORPHOLOGY_REQUIRED_COLUMNS)),
        "lcz": _table_schema_check(
            output_root / REQUIRED_FILES["lcz"],
            _flatten_column_groups(MORPHOLOGY_REQUIRED_COLUMNS) | LCZ_REQUIRED_COLUMNS,
        ),
        "risk": _table_schema_check(
            output_root / REQUIRED_FILES["risk"],
            _flatten_column_groups(MORPHOLOGY_REQUIRED_COLUMNS) | LCZ_REQUIRED_COLUMNS | RISK_REQUIRED_COLUMNS,
        ),
        "typical_blocks": _table_schema_check(
            output_root / REQUIRED_FILES["typical_blocks"],
            _flatten_column_groups(MORPHOLOGY_REQUIRED_COLUMNS) | LCZ_REQUIRED_COLUMNS | RISK_REQUIRED_COLUMNS | TYPICAL_BLOCK_REQUIRED_COLUMNS,
        ),
    }
    for key, summary in table_schema_summary.items():
        if summary.get("status") != "passed":
            errors.append(
                f"{key} table schema check failed: missing={summary.get('missing_columns')}, "
                f"null={summary.get('null_columns')}, status={summary.get('status')}"
            )
    table_value_summary = {
        key: _table_value_check(output_root / REQUIRED_FILES[key])
        for key in ["morphology", "lcz", "risk", "typical_blocks"]
    }
    for key, summary in table_value_summary.items():
        if summary.get("status") != "passed":
            errors.append(f"{key} table value check failed: {summary.get('errors')}")

    semantic_layer_summary = {
        "required_layer_tokens": required_layer_tokens,
        "required_layer_voxels": required_layer_voxels,
        "missing_required_layers": missing_required_layers,
        "layer_table_count": len(layer_table_names),
        "feature_counts": feature_counts,
        "dem_elevation_range_m": dem_elevation_range_m,
        "real_data_required": require_real_data_sources,
        "real_data_status": real_data_summary.get("status") if real_data_summary else None,
        "real_data_checks": real_data_summary.get("checks") if real_data_summary else None,
        "readiness_required": require_readiness_check,
        "readiness_check": site_summary.get("readiness_check") if site_summary else None,
    }

    result = {
        "status": "passed" if not errors else "failed",
        "output_root": str(output_root),
        "errors": errors,
        "warnings": warnings,
        "optional_missing": optional_missing,
        "file_checks": file_checks,
        "table_rows": table_rows,
        "table_schema_summary": table_schema_summary,
        "table_value_summary": table_value_summary,
        "rhino_summary": {
            "object_count": rhino_meta.get("object_count"),
            "layer_count": rhino_meta.get("layer_count"),
            "total_sparse_runs": rhino_meta.get("total_sparse_runs"),
            "total_voxels_represented": rhino_meta.get("total_voxels_represented"),
            "layer_voxel_counts": layer_voxel_counts,
            "file_read": rhino_file_summary,
        },
        "semantic_layer_summary": semantic_layer_summary,
        "preview_image_required": require_preview_image,
        "preview_image_summary": preview_image_summary,
        "site_consistency": {
            "origin_lat": origin_mapping.get("origin_lat"),
            "origin_lon": origin_mapping.get("origin_lon"),
            "aoi_width_m": voxel_grid.get("aoi_width_m"),
            "aoi_height_m": voxel_grid.get("aoi_height_m"),
            "voxel_size_m": voxel_grid.get("voxel_size_m"),
            "run_report_site_name": run_report.get("config", {}).get("site_name") if run_report else None,
        },
        "quality_status": quality.get("status"),
    }
    report_path = output_root / "12_logs" / "site_output_qa.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(result, ensure_ascii=True, indent=2), encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a generated site output bundle.")
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--min-buildings", type=int, default=1)
    parser.add_argument("--min-green-features", type=int, default=0)
    parser.add_argument("--min-dem-relief-m", type=float, default=0.0)
    parser.add_argument("--expected-lat", type=float, default=None)
    parser.add_argument("--expected-lon", type=float, default=None)
    parser.add_argument("--expected-aoi-width-m", type=float, default=None)
    parser.add_argument("--expected-voxel-size-m", type=float, default=None)
    parser.add_argument("--require-layer-token", action="append", default=[])
    parser.add_argument("--require-real-data-sources", action="store_true")
    parser.add_argument("--require-readiness-check", action="store_true")
    parser.add_argument("--allow-missing-preview-image", action="store_true")
    parser.add_argument("--coordinate-tolerance-deg", type=float, default=1e-5)
    parser.add_argument("--metric-tolerance-m", type=float, default=1e-6)
    args = parser.parse_args()
    result = qa_site_output(
        args.output_root,
        min_buildings=args.min_buildings,
        min_green_features=args.min_green_features,
        min_dem_relief_m=args.min_dem_relief_m,
        expected_lat=args.expected_lat,
        expected_lon=args.expected_lon,
        expected_aoi_width_m=args.expected_aoi_width_m,
        expected_voxel_size_m=args.expected_voxel_size_m,
        required_layer_tokens=args.require_layer_token,
        require_real_data_sources=args.require_real_data_sources,
        require_readiness_check=args.require_readiness_check,
        require_preview_image=not args.allow_missing_preview_image,
        coordinate_tolerance_deg=args.coordinate_tolerance_deg,
        metric_tolerance_m=args.metric_tolerance_m,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
