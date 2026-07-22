from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .paths import MorphologyPaths, ensure_output_dirs


def _clip01(value: float) -> float:
    if pd.isna(value):
        return 0.0
    return float(max(0.0, min(1.0, value)))


def _level(score: float) -> str:
    if score >= 0.75:
        return "very_high"
    if score >= 0.55:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def compute_heat_wind_risk(paths: MorphologyPaths) -> dict[str, Any]:
    ensure_output_dirs(paths)
    lcz_path = paths.lcz_dir / "lcz_classification_250m.csv"
    df = pd.read_csv(lcz_path)
    rows: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        heat_risk = (
            0.35 * _clip01(row.get("impervious_surface_ratio", 0.0))
            + 0.25 * _clip01(row.get("building_coverage_ratio", 0.0) / 0.5)
            + 0.20 * _clip01(row.get("floor_area_ratio_est", 0.0) / 2.5)
            + 0.20 * (1.0 - _clip01(row.get("blue_green_ratio", 0.0)))
        )
        low_ventilation_risk = (
            0.40 * _clip01(row.get("frontal_area_index_mean_proxy", 0.0) / 1.2)
            + 0.30 * _clip01(row.get("height_to_road_width_proxy", 0.0) / 2.0)
            + 0.30 * (1.0 - _clip01(row.get("ventilation_open_corridor_proxy", 0.0)))
        )
        exposure = (
            0.50 * _clip01(row.get("floor_area_ratio_est", 0.0) / 2.5)
            + 0.30 * _clip01(row.get("building_count", 0.0) / 20.0)
            + 0.20 * _clip01(row.get("road_centerline_length_m", 0.0) / 1200.0)
        )
        compound = 0.45 * heat_risk + 0.35 * low_ventilation_risk + 0.20 * exposure
        quality_flags = []
        if str(row.get("source_quality_flag", "")).startswith("low"):
            quality_flags.append("low_source_quality")
        if str(row.get("lcz_confidence_level", "")) == "low":
            quality_flags.append("low_lcz_confidence")
        if pd.isna(row.get("terrain_elevation_mean_m", np.nan)):
            quality_flags.append("missing_terrain")
        rows.append(
            {
                **row.to_dict(),
                "heat_risk_score": heat_risk,
                "heat_risk_level": _level(heat_risk),
                "low_ventilation_risk_score": low_ventilation_risk,
                "low_ventilation_risk_level": _level(low_ventilation_risk),
                "exposure_score": exposure,
                "exposure_level": _level(exposure),
                "heat_wind_compound_risk_score": compound,
                "heat_wind_compound_risk_level": _level(compound),
                "risk_data_sources": "morphology_indicators_250m.csv; lcz_classification_250m.csv; terrain_dem_samples.csv",
                "risk_quality_flags": ";".join(quality_flags) if quality_flags else "ok",
            }
        )
    out = pd.DataFrame(rows)
    csv_path = paths.risk_dir / "heat_wind_compound_risk_250m.csv"
    summary_path = paths.risk_dir / "heat_wind_compound_risk_summary.json"
    out.to_csv(csv_path, index=False, encoding="utf-8-sig")
    summary = {
        "status": "success",
        "grid_count": len(out),
        "compound_risk_counts": out["heat_wind_compound_risk_level"].value_counts().to_dict(),
        "quality_flag_counts": out["risk_quality_flags"].value_counts().to_dict(),
        "outputs": {"risk_csv": str(csv_path)},
        "method_note": "Phase 1 heat-wind compound risk only; not a full multi-hazard model.",
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    return summary
