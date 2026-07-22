from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd

from .paths import MorphologyPaths, ensure_output_dirs


def _check_layer(path: Path, expected_crs: int = 4326) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        result.update({"status": "missing"})
        return result
    try:
        gdf = gpd.read_file(path)
        result.update(
            {
                "status": "ok",
                "row_count": len(gdf),
                "crs": str(gdf.crs),
                "crs_ok": bool(gdf.crs is not None and gdf.crs.to_epsg() == expected_crs),
                "empty_geometry_count": int((gdf.geometry.isna() | gdf.geometry.is_empty).sum()) if "geometry" in gdf else 0,
            }
        )
    except Exception as exc:
        result.update({"status": "read_failed", "error": str(exc)})
    return result


def run_quality_control(paths: MorphologyPaths, require_outputs: bool = True) -> dict[str, Any]:
    ensure_output_dirs(paths)
    layer_checks = {
        "aoi": _check_layer(paths.aoi_path),
        "buildings": _check_layer(paths.buildings_path),
        "roads": _check_layer(paths.roads_path),
        "green": _check_layer(paths.green_path),
        "water": _check_layer(paths.water_path),
    }
    table_checks: dict[str, Any] = {}
    for name, path in {
        "morphology": paths.morphology_dir / "morphology_indicators_250m.csv",
        "lcz": paths.lcz_dir / "lcz_classification_250m.csv",
        "risk": paths.risk_dir / "heat_wind_compound_risk_250m.csv",
    }.items():
        if not path.exists():
            table_checks[name] = {
                "path": str(path),
                "exists": False,
                "status": "missing" if require_outputs else "pending_until_later_notebook",
            }
            continue
        df = pd.read_csv(path)
        numeric = df.select_dtypes(include=[np.number])
        missing_ratio = float(df.isna().sum().sum() / max(df.shape[0] * df.shape[1], 1))
        outlier_fields = {}
        bounded_ratio_fields = {col for col in numeric.columns if col.endswith("_ratio")}
        bounded_score_fields = {col for col in numeric.columns if col.endswith("_score")}
        bounded_fields = bounded_ratio_fields | bounded_score_fields
        bounded_fields.update({"lcz_top1_probability", "lcz_top2_probability", "lcz_entropy_norm"})
        for col in numeric.columns:
            values = numeric[col].dropna()
            if values.empty:
                continue
            if col in bounded_fields:
                outlier_fields[col] = int(((values < -1e-6) | (values > 1.5)).sum())
            elif col.endswith("_proxy"):
                outlier_fields[col] = int((values < -1e-6).sum())
        low_conf = int((df.get("lcz_confidence_level", pd.Series(dtype=str)).astype(str) == "low").sum()) if "lcz_confidence_level" in df else 0
        table_checks[name] = {
            "path": str(path),
            "exists": True,
            "row_count": len(df),
            "column_count": len(df.columns),
            "missing_ratio": missing_ratio,
            "outlier_field_counts": outlier_fields,
            "low_lcz_confidence_count": low_conf,
        }

    hard_errors = []
    for key, check in layer_checks.items():
        if not check.get("exists") or check.get("status") != "ok":
            hard_errors.append(f"{key} layer missing or unreadable")
        if check.get("exists") and not check.get("crs_ok", True):
            hard_errors.append(f"{key} CRS is not EPSG:4326")
    for key, check in table_checks.items():
        if require_outputs and not check.get("exists"):
            hard_errors.append(f"{key} table missing")
    report = {
        "status": "passed" if not hard_errors else "needs_attention",
        "require_outputs": require_outputs,
        "hard_errors": hard_errors,
        "layer_checks": layer_checks,
        "table_checks": table_checks,
        "known_limits": [
            "LCZ phase 1 thresholds are rule/prototype based and require local calibration.",
            "Heat-wind risk is a morphology proxy, not a calibrated thermal or CFD simulation result.",
        ],
    }
    json_path = paths.audit_dir / "morphology_lcz_risk_quality_report.json"
    md_path = paths.audit_dir / "morphology_lcz_risk_quality_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    lines = ["# Morphology LCZ Risk Quality Report", "", f"Status: `{report['status']}`", ""]
    if hard_errors:
        lines.extend(["## Issues", *[f"- {item}" for item in hard_errors], ""])
    lines.append("## Layer Checks")
    for key, check in layer_checks.items():
        lines.append(f"- {key}: {check}")
    lines.append("")
    lines.append("## Table Checks")
    for key, check in table_checks.items():
        lines.append(f"- {key}: {check}")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return report
