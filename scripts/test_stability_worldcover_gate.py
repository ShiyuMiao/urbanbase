from __future__ import annotations

import json
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from run_stability_checks import has_soft_warning, has_worldcover_coverage_gap, warning_labels_excluding_failures


def main() -> None:
    missing_worldcover = {
        "label": "worldcover_coverage_audit",
        "parsed_summary": {
            "status": "completed_with_missing_tiles",
            "missing_expected_tiles": ["ESA_WorldCover_10m_2021_v200_N39E114_Map.tif"],
        },
    }
    clean_worldcover = {
        "label": "worldcover_coverage_audit",
        "parsed_summary": {
            "status": "success",
            "missing_expected_tiles": [],
        },
    }
    unrelated_missing = {
        "label": "other_check",
        "parsed_summary": {
            "status": "completed_with_missing_tiles",
            "missing_expected_tiles": ["ESA_WorldCover_10m_2021_v200_N39E114_Map.tif"],
        },
    }
    implicit_missing = {
        "label": "worldcover_coverage_audit",
        "parsed_summary": {
            "status": "success",
            "missing_expected_tiles": ["ESA_WorldCover_10m_2021_v200_N39E114_Map.tif"],
        },
    }

    if not has_worldcover_coverage_gap(missing_worldcover):
        raise AssertionError("Strict WorldCover gate should catch completed_with_missing_tiles.")
    if not has_worldcover_coverage_gap(implicit_missing):
        raise AssertionError("Strict WorldCover gate should catch non-empty missing_expected_tiles.")
    if has_worldcover_coverage_gap(clean_worldcover):
        raise AssertionError("Strict WorldCover gate should not fail clean coverage.")
    if has_worldcover_coverage_gap(unrelated_missing):
        raise AssertionError("Strict WorldCover gate should be scoped to worldcover_coverage_audit.")
    if not has_soft_warning(missing_worldcover):
        raise AssertionError("Missing WorldCover coverage should remain visible as a soft warning in default mode.")
    if warning_labels_excluding_failures([missing_worldcover], [missing_worldcover]):
        raise AssertionError("Failed strict WorldCover coverage should not be duplicated as a warning.")
    if warning_labels_excluding_failures([missing_worldcover], []) != ["worldcover_coverage_audit"]:
        raise AssertionError("Default missing WorldCover coverage should remain a warning when it is not failed.")

    print(
        json.dumps(
            {
                "status": "success",
                "strict_missing_tile_gate": "passed",
                "default_soft_warning": "passed",
                "strict_warning_deduplication": "passed",
                "clean_coverage_passthrough": "passed",
                "label_scope": "passed",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
