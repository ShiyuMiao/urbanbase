from __future__ import annotations

import contextlib
import io
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = PROJECT_ROOT / "notebooks"
REQUIRED_NOTEBOOKS = [
    "01_study_area_grid_prepare.ipynb",
    "02_voxcity_semantic_layers_check.ipynb",
    "03_morphology_indicator_extraction.ipynb",
    "04_lcz_classification_uncertainty.ipynb",
    "05_heat_wind_compound_risk.ipynb",
    "06_visualization_typical_blocks_export.ipynb",
]


def cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(item) for item in source)
    return str(source)


def execute_notebook_sequence() -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    ns: dict[str, Any] = {"__name__": "__main__"}
    for name in REQUIRED_NOTEBOOKS:
        path = NOTEBOOK_DIR / name
        if not path.exists():
            failures.append({"notebook": name, "cell": None, "error": f"Missing notebook: {path}"})
            break
        notebook = json.loads(path.read_text(encoding="utf-8"))
        for idx, cell in enumerate(notebook.get("cells", [])):
            if cell.get("cell_type") != "code":
                continue
            source = cell_source(cell)
            stdout = io.StringIO()
            stderr = io.StringIO()
            started = time.perf_counter()
            try:
                with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                    exec(compile(source, f"{name}:cell_{idx}", "exec"), ns)
                results.append(
                    {
                        "notebook": name,
                        "cell": idx,
                        "status": "passed",
                        "seconds": round(time.perf_counter() - started, 3),
                        "stdout_tail": stdout.getvalue()[-1000:],
                        "stderr_tail": stderr.getvalue()[-1000:],
                    }
                )
            except Exception as exc:
                failures.append(
                    {
                        "notebook": name,
                        "cell": idx,
                        "error": str(exc),
                        "traceback_tail": traceback.format_exc().splitlines()[-12:],
                    }
                )
                results.append(
                    {
                        "notebook": name,
                        "cell": idx,
                        "status": "failed",
                        "seconds": round(time.perf_counter() - started, 3),
                        "stdout_tail": stdout.getvalue()[-1000:],
                        "stderr_tail": stderr.getvalue()[-1000:],
                    }
                )
                break
        if failures:
            break
    return {
        "status": "passed" if not failures else "failed",
        "notebook_dir": str(NOTEBOOK_DIR),
        "required_notebooks": REQUIRED_NOTEBOOKS,
        "executed_cell_count": len(results),
        "failures": failures,
        "results": results,
    }


def main() -> None:
    summary = execute_notebook_sequence()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    raise SystemExit(0 if summary["status"] == "passed" else 1)


if __name__ == "__main__":
    main()
