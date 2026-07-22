from __future__ import annotations

import contextlib
import io
import json
import sys
import time
import traceback
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK = PROJECT_ROOT / "CityLBM_VoxCity_China_0p1m_RhinoVoxel_full_process.ipynb"
EXECUTED = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "12_logs" / "CityLBM_VoxCity_China_0p1m_RhinoVoxel_full_process.executed.ipynb"


def execute_notebook() -> int:
    nb = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    ns = {"__name__": "__main__", "__file__": str(NOTEBOOK)}
    failures = []
    for idx, cell in enumerate(nb.get("cells", [])):
        if cell.get("cell_type") != "code":
            continue
        source = "".join(cell.get("source", []))
        stdout = io.StringIO()
        stderr = io.StringIO()
        started = time.perf_counter()
        outputs = []
        try:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                exec(compile(source, f"{NOTEBOOK.name}:cell_{idx}", "exec"), ns)
            if stdout.getvalue():
                outputs.append({"output_type": "stream", "name": "stdout", "text": stdout.getvalue().splitlines(True)})
            if stderr.getvalue():
                outputs.append({"output_type": "stream", "name": "stderr", "text": stderr.getvalue().splitlines(True)})
            cell["execution_count"] = idx + 1
            cell["outputs"] = outputs
            cell.setdefault("metadata", {})["execution"] = {"status": "success", "seconds": round(time.perf_counter() - started, 3)}
        except Exception as exc:
            tb = traceback.format_exc()
            outputs.append({"output_type": "stream", "name": "stdout", "text": stdout.getvalue().splitlines(True)})
            outputs.append({"output_type": "error", "ename": exc.__class__.__name__, "evalue": str(exc), "traceback": tb.splitlines()})
            cell["execution_count"] = idx + 1
            cell["outputs"] = outputs
            cell.setdefault("metadata", {})["execution"] = {"status": "failed", "seconds": round(time.perf_counter() - started, 3)}
            failures.append({"cell": idx, "error": str(exc)})
            break
    EXECUTED.parent.mkdir(parents=True, exist_ok=True)
    nb.setdefault("metadata", {})["citylbm_execution"] = {
        "runner": "scripts/run_notebook.py",
        "finished_with_failures": failures,
        "executed_path": str(EXECUTED.relative_to(PROJECT_ROOT)),
    }
    EXECUTED.write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"executed_notebook": str(EXECUTED), "failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(execute_notebook())
