from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from .grid import load_grid_local
from .paths import MorphologyPaths, ensure_output_dirs


def make_morphology_figures(paths: MorphologyPaths) -> dict[str, Any]:
    ensure_output_dirs(paths)
    risk = pd.read_csv(paths.risk_dir / "heat_wind_compound_risk_250m.csv")
    grid = load_grid_local(paths)[["grid_id", "geometry"]]
    gdf = gpd.GeoDataFrame(risk.merge(grid, on="grid_id", how="left"), geometry="geometry")
    outputs: dict[str, str] = {}
    for field, filename, title in [
        ("building_coverage_ratio", "morphology_building_coverage_250m.png", "Building coverage ratio"),
        ("lcz_top1_probability", "lcz_top1_probability_250m.png", "LCZ top1 probability"),
        ("heat_wind_compound_risk_score", "heat_wind_compound_risk_250m.png", "Heat-wind compound risk"),
    ]:
        fig, ax = plt.subplots(figsize=(6, 5), dpi=180)
        gdf.plot(column=field, ax=ax, legend=True, cmap="viridis", edgecolor="#333", linewidth=0.5)
        ax.set_title(title)
        ax.set_aspect("equal")
        ax.set_axis_off()
        fig.tight_layout()
        out = paths.figures_dir / filename
        fig.savefig(out)
        plt.close(fig)
        outputs[field] = str(out)
    summary = {"status": "success", "outputs": outputs}
    (paths.figures_dir / "morphology_lcz_risk_figure_summary.json").write_text(
        json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8"
    )
    return summary
