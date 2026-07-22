from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .grid import prepare_grid
from .indicators import extract_morphology_indicators
from .lcz import classify_lcz
from .paths import MorphologyPaths, default_paths, ensure_output_dirs
from .quality import run_quality_control
from .risk import compute_heat_wind_risk
from .typical_blocks import select_typical_blocks
from .visualization import make_morphology_figures


def run_full_workflow(
    project_root: str | Path | None = None,
    output_root: str | Path | None = None,
    grid_size_m: float = 250.0,
    typical_count: int = 5,
) -> dict[str, Any]:
    paths = default_paths(project_root=project_root, output_root=output_root)
    ensure_output_dirs(paths)
    report = {
        "prepare_grid": prepare_grid(paths, grid_size_m=grid_size_m),
        "extract_morphology_indicators": extract_morphology_indicators(paths, grid_size_m=grid_size_m),
        "classify_lcz": classify_lcz(paths),
        "compute_heat_wind_risk": compute_heat_wind_risk(paths),
        "select_typical_blocks": select_typical_blocks(paths, count=typical_count),
        "make_morphology_figures": make_morphology_figures(paths),
        "quality_control": run_quality_control(paths),
    }
    summary_path = paths.output_root / "12_logs" / "morphology_lcz_risk_workflow_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(report, ensure_ascii=True, indent=2), encoding="utf-8")
    return report
