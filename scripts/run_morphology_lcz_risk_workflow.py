from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from urban_morphology.workflow import run_full_workflow


def main() -> None:
    parser = argparse.ArgumentParser(description="Run 250 m morphology, LCZ, and heat-wind risk workflow.")
    parser.add_argument("--project-root", default=str(PROJECT_ROOT))
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--grid-size-m", type=float, default=250.0)
    parser.add_argument("--typical-count", type=int, default=5)
    args = parser.parse_args()
    report = run_full_workflow(
        project_root=args.project_root,
        output_root=args.output_root,
        grid_size_m=args.grid_size_m,
        typical_count=args.typical_count,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
