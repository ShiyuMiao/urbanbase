from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from china_voxel_pipeline import (  # noqa: E402
    OUTPUT_ROOT,
    RunConfig,
    config_output_root,
    osm_shared_cache_path,
    rel_project_path,
    safe_filename,
    write_json,
)
from run_site_model import build_request  # noqa: E402


CORE_FEATURE_KEYS = ("building_way_count", "highway_way_count")


def request_namespace(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=args.site_name,
        site_name_cn=args.site_name_cn or args.site_name,
        lat=args.lat,
        lon=args.lon,
        input_crs=args.input_crs,
        half_size_m=args.half_size_m,
        voxel_size_m=args.voxel_size_m,
        output_root=args.output_root,
    )


def site_cache_paths(args: argparse.Namespace) -> list[Path]:
    request = build_request(request_namespace(args))
    config = RunConfig(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        center_lat=request.center_lat_wgs84,
        center_lon=request.center_lon_wgs84,
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        output_root=request.output_root,
        strict_real_data=True,
    )
    root = config_output_root(config)
    return [
        root / "01_raw" / f"osm_overpass_combined_raw_{safe_filename(config.site_name)}.json",
        osm_shared_cache_path(config),
    ]


def load_json(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, str(exc)
    if not isinstance(data, dict):
        return None, "cache root is not a JSON object"
    return data, None


def osm_cache_counts(raw: dict[str, Any]) -> dict[str, int]:
    counts = {
        "element_count": 0,
        "node_count": 0,
        "way_count": 0,
        "building_way_count": 0,
        "highway_way_count": 0,
        "green_way_count": 0,
        "water_way_count": 0,
        "poi_node_count": 0,
        "referenced_node_count": 0,
        "missing_node_reference_count": 0,
        "missing_node_reference_way_count": 0,
        "closed_building_way_count": 0,
        "unresolved_building_way_count": 0,
        "unresolved_highway_way_count": 0,
    }
    elements = raw.get("elements", [])
    if not isinstance(elements, list):
        return counts

    node_ids = {element.get("id") for element in elements if element.get("type") == "node"}
    referenced_nodes: set[int] = set()
    for element in elements:
        counts["element_count"] += 1
        element_type = element.get("type")
        tags = element.get("tags", {}) or {}
        if element_type == "node":
            counts["node_count"] += 1
            if any(key in tags for key in ("amenity", "shop", "tourism", "public_transport")):
                counts["poi_node_count"] += 1
            continue
        if element_type != "way":
            continue
        counts["way_count"] += 1
        node_refs = [node for node in element.get("nodes", []) if isinstance(node, int)]
        referenced_nodes.update(node_refs)
        missing_refs = [node for node in node_refs if node not in node_ids]
        if missing_refs:
            counts["missing_node_reference_count"] += len(missing_refs)
            counts["missing_node_reference_way_count"] += 1
        if "building" in tags:
            counts["building_way_count"] += 1
            if len(node_refs) >= 4 and node_refs[0] == node_refs[-1]:
                counts["closed_building_way_count"] += 1
            if missing_refs:
                counts["unresolved_building_way_count"] += 1
        if "highway" in tags:
            counts["highway_way_count"] += 1
            if missing_refs:
                counts["unresolved_highway_way_count"] += 1
        if any(key in tags for key in ("leisure", "landuse", "natural")):
            counts["green_way_count"] += 1
        if tags.get("natural") == "water" or "waterway" in tags:
            counts["water_way_count"] += 1
    counts["referenced_node_count"] = len(referenced_nodes)
    return counts


def validate_cache(path: Path, require_core_features: bool) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(path),
        "relative_path": rel_project_path(path),
        "exists": path.exists(),
        "status": "missing",
        "errors": [],
        "warnings": [],
        "counts": {},
        "fallback_reason": None,
    }
    if not path.exists():
        result["errors"].append("file_missing")
        return result
    result["bytes"] = path.stat().st_size
    raw, error = load_json(path)
    if raw is None:
        result["status"] = "unreadable"
        result["errors"].append(f"json_unreadable:{error}")
        return result

    fallback_reason = raw.get("fallback_reason")
    result["fallback_reason"] = fallback_reason
    if fallback_reason:
        result["errors"].append("fallback_empty_cache")
    if not isinstance(raw.get("elements"), list):
        result["errors"].append("missing_elements_array")

    counts = osm_cache_counts(raw)
    result["counts"] = counts
    if counts["element_count"] <= 0 and require_core_features:
        result["errors"].append("empty_elements")
    elif counts["element_count"] <= 0:
        result["warnings"].append("empty_elements")
    if counts["node_count"] <= 0 and counts["way_count"] > 0:
        result["errors"].append("ways_without_nodes")
    if require_core_features and not any(counts[key] > 0 for key in CORE_FEATURE_KEYS):
        result["errors"].append("missing_building_or_highway_core_features")
    if counts["building_way_count"] and counts["closed_building_way_count"] == 0:
        result["warnings"].append("building_ways_are_not_closed")
    if counts["missing_node_reference_count"]:
        result["errors"].append("unresolved_way_node_references")

    result["status"] = "valid" if not result["errors"] else "invalid"
    return result


def unique_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    unique: list[Path] = []
    for path in paths:
        resolved = str(path)
        if resolved in seen:
            continue
        seen.add(resolved)
        unique.append(path)
    return unique


def validate_osm_caches(
    cache_paths: list[Path],
    output_json: Path | None,
    strict: bool,
    require_core_features: bool = True,
) -> dict[str, Any]:
    reports = [validate_cache(path, require_core_features) for path in unique_paths(cache_paths)]
    valid = [item for item in reports if item["status"] == "valid"]
    invalid = [item for item in reports if item["status"] in {"invalid", "unreadable"}]
    missing = [item for item in reports if item["status"] == "missing"]
    if valid:
        status = "success"
    elif strict:
        status = "failed_missing_or_invalid_cache"
    elif invalid or missing:
        status = "completed_with_cache_gaps"
    else:
        status = "success"
    report = {
        "status": status,
        "strict": strict,
        "require_core_features": require_core_features,
        "output_json": str(output_json) if output_json else None,
        "cache_count": len(reports),
        "valid_cache_count": len(valid),
        "invalid_cache_count": len(invalid),
        "missing_cache_count": len(missing),
        "selected_cache": valid[0]["path"] if valid else None,
        "selected_counts": valid[0]["counts"] if valid else {},
        "invalid_caches": [item["path"] for item in invalid],
        "missing_caches": [item["path"] for item in missing],
        "caches": reports,
    }
    if output_json:
        write_json(output_json, report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate cached OSM/Overpass JSON before formal VoxCity modeling.")
    parser.add_argument("--cache-path", action="append", type=Path, default=[], help="Explicit OSM cache JSON to validate. Can be repeated.")
    parser.add_argument("--site-name", help="ASCII-safe site id. Used with lat/lon to derive site and shared OSM cache paths.")
    parser.add_argument("--site-name-cn", default="", help="Human-readable site name.")
    parser.add_argument("--lat", type=float)
    parser.add_argument("--lon", type=float)
    parser.add_argument("--input-crs", default="WGS84", choices=["WGS84", "EPSG:4326", "GCJ02", "GCJ-02", "AMAP", "GAODE"])
    parser.add_argument("--half-size-m", type=float, default=250.0)
    parser.add_argument("--voxel-size-m", type=float, default=1.0)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--output-json", type=Path, default=OUTPUT_ROOT / "12_logs" / "osm_cache_validation.json")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero unless at least one valid cache is available.")
    parser.add_argument("--allow-no-core-features", action="store_true", help="Do not require building or highway ways.")
    args = parser.parse_args()

    cache_paths = list(args.cache_path)
    if args.site_name:
        if args.lat is None or args.lon is None:
            parser.error("--lat and --lon are required with --site-name")
        cache_paths.extend(site_cache_paths(args))
    if not cache_paths:
        parser.error("provide --cache-path or --site-name with --lat/--lon")

    result = validate_osm_caches(cache_paths, args.output_json, args.strict, not args.allow_no_core_features)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(1 if result["status"].startswith("failed") else 0)


if __name__ == "__main__":
    main()
