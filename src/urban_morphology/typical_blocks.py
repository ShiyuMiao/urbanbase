from __future__ import annotations

import json
import warnings
from typing import Any

import geopandas as gpd
import pandas as pd

from .grid import load_grid_local
from .paths import MorphologyPaths, ensure_output_dirs


def select_typical_blocks(paths: MorphologyPaths, count: int = 5) -> dict[str, Any]:
    ensure_output_dirs(paths)
    risk = pd.read_csv(paths.risk_dir / "heat_wind_compound_risk_250m.csv")
    grid = load_grid_local(paths)[["grid_id", "geometry"]]
    candidates = risk.copy()
    candidates["selection_score"] = (
        candidates["heat_wind_compound_risk_score"].astype(float)
        + 0.10 * candidates["lcz_top1_probability"].astype(float)
        - 0.05 * candidates["lcz_entropy_norm"].astype(float)
    )
    risk_order = {"very_high": 4, "high": 3, "medium": 2, "low": 1}
    candidates["risk_rank"] = candidates["heat_wind_compound_risk_level"].map(risk_order).fillna(0)
    candidates = candidates.sort_values(["risk_rank", "selection_score"], ascending=[False, False])
    # Keep a spread across LCZ labels before filling by score.
    selected_rows = []
    seen_lcz: set[str] = set()
    for _, row in candidates.sort_values("selection_score", ascending=False).iterrows():
        label = str(row["lcz_probability_top1"])
        if label in seen_lcz:
            continue
        selected_rows.append(row)
        seen_lcz.add(label)
        if len(selected_rows) >= count:
            break
    if len(selected_rows) < count:
        selected_ids = {str(r["grid_id"]) for r in selected_rows}
        for _, row in candidates.sort_values("selection_score", ascending=False).iterrows():
            if str(row["grid_id"]) in selected_ids:
                continue
            selected_rows.append(row)
            selected_ids.add(str(row["grid_id"]))
            if len(selected_rows) >= count:
                break
    selected = pd.DataFrame(selected_rows)
    selected = selected.head(count)
    csv_path = paths.typical_dir / "typical_blocks_for_citylbm.csv"
    geojson_path = paths.typical_dir / "typical_blocks_for_citylbm.geojson"
    selected.to_csv(csv_path, index=False, encoding="utf-8-sig")
    merged = gpd.GeoDataFrame(selected.merge(grid, on="grid_id", how="left"), geometry="geometry")
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="'crs' was not provided.*")
        merged.to_file(geojson_path, driver="GeoJSON")
    summary = {
        "status": "success",
        "selected_count": len(selected),
        "selected_grid_ids": selected["grid_id"].astype(str).tolist(),
        "outputs": {"csv": str(csv_path), "geojson": str(geojson_path)},
    }
    (paths.typical_dir / "typical_blocks_summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return summary
