from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from urban_morphology.workflow import run_full_workflow


REQUIRED_MORPHOLOGY_COLUMNS = {
    "grid_id",
    "area_m2",
    "center_lon",
    "center_lat",
    "building_count",
    "building_coverage_ratio",
    "building_height_mean_m",
    "open_space_ratio",
    "frontal_area_index_mean_proxy",
    "green_ratio",
    "tree_cover_ratio",
    "water_ratio",
    "terrain_elevation_mean_m",
    "terrain_relief_m",
}

REQUIRED_LCZ_COLUMNS = {
    "grid_id",
    "lcz_rule",
    "lcz_probability_top1",
    "lcz_probability_top2",
    "lcz_top1_probability",
    "lcz_top1_top2_margin",
    "lcz_entropy",
    "lcz_entropy_norm",
    "lcz_confidence_level",
}

REQUIRED_RISK_COLUMNS = {
    "grid_id",
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


def _assert_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    missing = sorted(required - set(df.columns))
    if missing:
        raise AssertionError(f"{label} missing required columns: {missing}")


def _assert_probability_bounds(df: pd.DataFrame) -> None:
    for col in ["lcz_top1_probability", "lcz_top2_probability", "lcz_top1_top2_margin", "lcz_entropy_norm"]:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().any():
            raise AssertionError(f"{col} contains NaN")
    if not ((df["lcz_top1_probability"] >= 0) & (df["lcz_top1_probability"] <= 1)).all():
        raise AssertionError("lcz_top1_probability outside [0, 1]")
    if not ((df["lcz_top1_top2_margin"] >= -1e-9) & (df["lcz_top1_top2_margin"] <= 1)).all():
        raise AssertionError("lcz_top1_top2_margin outside [0, 1]")
    if not ((df["lcz_entropy_norm"] >= 0) & (df["lcz_entropy_norm"] <= 1.000001)).all():
        raise AssertionError("lcz_entropy_norm outside [0, 1]")


def _assert_score_bounds(df: pd.DataFrame) -> None:
    score_cols = [col for col in df.columns if col.endswith("_score")]
    for col in score_cols:
        values = pd.to_numeric(df[col], errors="coerce")
        if values.isna().any():
            raise AssertionError(f"{col} contains NaN")
        if not ((values >= -1e-9) & (values <= 1.000001)).all():
            raise AssertionError(f"{col} outside [0, 1]")


def _assert_notebooks_parse() -> None:
    for path in sorted((PROJECT_ROOT / "notebooks").glob("0*_*.ipynb")):
        with path.open("r", encoding="utf-8-sig") as f:
            json.load(f)


def _assert_machine_json_is_ascii(paths: list[Path]) -> None:
    for path in paths:
        text = path.read_text(encoding="utf-8")
        json.loads(text)
        try:
            text.encode("ascii")
        except UnicodeEncodeError as exc:
            raise AssertionError(f"{path} should be ASCII-escaped machine JSON") from exc


def main() -> None:
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        report = run_full_workflow(project_root=PROJECT_ROOT, grid_size_m=250.0, typical_count=5)
    unexpected_warnings = [
        str(item.message)
        for item in caught
        if "'crs' was not provided" in str(item.message)
    ]
    if unexpected_warnings:
        raise AssertionError(f"Unexpected CRS warnings were emitted: {unexpected_warnings}")

    output_root = PROJECT_ROOT / "outputs_citylbm_voxel_china"
    morphology = pd.read_csv(output_root / "08_morphology" / "morphology_indicators_250m.csv")
    lcz = pd.read_csv(output_root / "09_lcz" / "lcz_classification_250m.csv")
    risk = pd.read_csv(output_root / "14_heat_wind_risk" / "heat_wind_compound_risk_250m.csv")
    typical = pd.read_csv(output_root / "15_typical_blocks" / "typical_blocks_for_citylbm.csv")
    quality = json.loads((output_root / "07_audit" / "morphology_lcz_risk_quality_report.json").read_text(encoding="utf-8"))
    _assert_machine_json_is_ascii(
        [
            output_root / "08_morphology" / "grid_prepare_summary.json",
            output_root / "08_morphology" / "morphology_indicator_schema.json",
            output_root / "09_lcz" / "lcz_classification_summary.json",
            output_root / "14_heat_wind_risk" / "heat_wind_compound_risk_summary.json",
            output_root / "15_typical_blocks" / "typical_blocks_summary.json",
            output_root / "10_figures" / "morphology_lcz_risk_figure_summary.json",
            output_root / "07_audit" / "morphology_lcz_risk_quality_report.json",
            output_root / "12_logs" / "morphology_lcz_risk_workflow_summary.json",
        ]
    )

    if len(morphology) == 0:
        raise AssertionError("morphology table is empty")
    if len(morphology) != len(lcz) or len(lcz) != len(risk):
        raise AssertionError("morphology, LCZ, and risk row counts differ")
    if not (3 <= len(typical) <= 5) and len(morphology) >= 3:
        raise AssertionError("typical block count should be between 3 and 5 when enough grids exist")
    if len(morphology) < 3 and len(typical) != len(morphology):
        raise AssertionError("typical block count should match available grid count for tiny AOIs")

    _assert_columns(morphology, REQUIRED_MORPHOLOGY_COLUMNS, "morphology")
    _assert_columns(lcz, REQUIRED_LCZ_COLUMNS, "lcz")
    _assert_columns(risk, REQUIRED_RISK_COLUMNS, "risk")
    _assert_probability_bounds(lcz)
    _assert_score_bounds(risk)
    _assert_notebooks_parse()

    if quality.get("status") != "passed":
        raise AssertionError(f"quality report did not pass: {quality.get('hard_errors')}")
    if report["quality_control"]["status"] != "passed":
        raise AssertionError("workflow summary quality_control did not pass")

    print(
        json.dumps(
            {
                "status": "success",
                "grid_count": len(morphology),
                "morphology_columns": len(morphology.columns),
                "lcz_confidence_counts": lcz["lcz_confidence_level"].value_counts().to_dict(),
                "risk_level_counts": risk["heat_wind_compound_risk_level"].value_counts().to_dict(),
                "typical_block_count": len(typical),
                "quality_status": quality.get("status"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
