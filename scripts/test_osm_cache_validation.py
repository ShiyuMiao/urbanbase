from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from validate_osm_cache import validate_osm_caches  # noqa: E402


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    output_root = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "_osm_validation_tests"
    real_cache = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "01_raw" / "osm_overpass_combined_aoi_aa5947f4c5703a86.json"
    fallback_cache = output_root / "fallback_empty_osm.json"
    empty_real_cache = output_root / "empty_real_osm.json"
    unresolved_cache = output_root / "unresolved_way_nodes_osm.json"

    write_json(fallback_cache, {"elements": [], "fallback_reason": "synthetic unavailable"})
    write_json(empty_real_cache, {"elements": []})
    write_json(
        unresolved_cache,
        {
            "elements": [
                {"type": "way", "id": 1, "nodes": [101, 102, 101], "tags": {"highway": "service"}},
            ]
        },
    )

    valid_report = validate_osm_caches([real_cache], output_root / "valid_osm_cache_validation.json", strict=True)
    fallback_report = validate_osm_caches([fallback_cache], None, strict=True)
    empty_default_report = validate_osm_caches([empty_real_cache], None, strict=True)
    empty_allowed_report = validate_osm_caches([empty_real_cache], None, strict=True, require_core_features=False)
    unresolved_report = validate_osm_caches([unresolved_cache], None, strict=True)
    errors: list[str] = []

    if valid_report.get("status") != "success":
        errors.append(f"Dalian cached OSM should validate successfully: {valid_report.get('status')}")
    counts = valid_report.get("selected_counts", {})
    if counts.get("building_way_count", 0) <= 0:
        errors.append(f"Dalian OSM cache should contain building ways: {counts}")
    if counts.get("highway_way_count", 0) <= 0:
        errors.append(f"Dalian OSM cache should contain highway ways: {counts}")
    if counts.get("missing_node_reference_count", 0) != 0:
        errors.append(f"Dalian OSM cache should have resolved way nodes: {counts}")
    if fallback_report.get("status") != "failed_missing_or_invalid_cache":
        errors.append(f"fallback cache should fail in strict mode: {fallback_report.get('status')}")
    fallback_errors = fallback_report.get("caches", [{}])[0].get("errors", [])
    if "fallback_empty_cache" not in fallback_errors:
        errors.append(f"fallback cache should report fallback_empty_cache: {fallback_errors}")
    if empty_default_report.get("status") != "failed_missing_or_invalid_cache":
        errors.append(f"empty real cache should fail when core features are required: {empty_default_report.get('status')}")
    if empty_allowed_report.get("status") != "success":
        errors.append(f"empty real cache should pass when core features are not required: {empty_allowed_report.get('status')}")
    empty_allowed_warnings = empty_allowed_report.get("caches", [{}])[0].get("warnings", [])
    if "empty_elements" not in empty_allowed_warnings:
        errors.append(f"empty real cache should keep an empty_elements warning: {empty_allowed_warnings}")
    unresolved_errors = unresolved_report.get("caches", [{}])[0].get("errors", [])
    if "unresolved_way_node_references" not in unresolved_errors:
        errors.append(f"unresolved way cache should report node reference errors: {unresolved_errors}")

    result = {
        "status": "success" if not errors else "failed",
        "errors": errors,
        "valid_cache": str(real_cache),
        "valid_status": valid_report.get("status"),
        "valid_cache_count": valid_report.get("valid_cache_count"),
        "invalid_cache_count": valid_report.get("invalid_cache_count"),
        "missing_cache_count": valid_report.get("missing_cache_count"),
        "selected_cache": valid_report.get("selected_cache"),
        "selected_counts": valid_report.get("selected_counts"),
        "valid_counts": counts,
        "fallback_status": fallback_report.get("status"),
        "empty_default_status": empty_default_report.get("status"),
        "empty_allowed_status": empty_allowed_report.get("status"),
        "unresolved_status": unresolved_report.get("status"),
        "output_json": valid_report.get("output_json"),
    }
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0 if result["status"] == "success" else 1)


if __name__ == "__main__":
    main()
