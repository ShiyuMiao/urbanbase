from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from china_voxel_pipeline import (  # noqa: E402
    RunConfig,
    discover_esa_worldcover_candidates,
    ensure_dirs,
    rel_project_path,
    write_json,
)

try:
    import rasterio
    from rasterio.warp import transform_bounds
except Exception:  # pragma: no cover - optional dependency report path
    rasterio = None
    transform_bounds = None


@dataclass(frozen=True)
class AuditSite:
    name: str
    lat: float
    lon: float


DEFAULT_SITES = [
    AuditSite("dalian_dlut_west_library", 38.8831553, 121.5120457),
    AuditSite("dalian_zhongshan_square", 38.9213, 121.6439),
    AuditSite("beijing_core_probe", 39.9042, 116.4074),
    AuditSite("shanghai_core_probe", 31.2304, 121.4737),
    AuditSite("chengdu_core_probe", 30.5728, 104.0668),
    AuditSite("shenzhen_core_probe", 22.5431, 114.0579),
    AuditSite("urumqi_core_probe", 43.8256, 87.6168),
    AuditSite("harbin_core_probe", 45.8038, 126.5349),
]


TILE_RE = re.compile(r"(N\d{2}|S\d{2})(E\d{3}|W\d{3})", re.IGNORECASE)


def parse_site(value: str) -> AuditSite:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("--site must use name,lat,lon")
    name, lat, lon = parts
    try:
        return AuditSite(name=name, lat=float(lat), lon=float(lon))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--site lat and lon must be numeric") from exc


def parse_tile_prefix(path: Path) -> str | None:
    match = TILE_RE.search(path.name)
    if not match:
        return None
    return f"{match.group(1).upper()}{match.group(2).upper()}"


def candidate_record(path: Path) -> dict[str, Any]:
    record: dict[str, Any] = {
        "path": str(path),
        "relative_path": rel_project_path(path),
        "name": path.name,
        "tile_prefix": parse_tile_prefix(path),
    }
    try:
        stat = path.stat()
        record["bytes"] = stat.st_size
        record["modified_time"] = stat.st_mtime
    except OSError as exc:
        record["stat_error"] = str(exc)
    if rasterio is None:
        record["raster_status"] = "unchecked_missing_rasterio"
        return record
    try:
        with rasterio.open(path) as src:
            record["crs"] = str(src.crs) if src.crs else None
            record["bounds"] = [float(v) for v in src.bounds]
            record["width"] = int(src.width)
            record["height"] = int(src.height)
            if src.crs and transform_bounds is not None:
                record["bounds_wgs84"] = [
                    float(v) for v in transform_bounds(src.crs, "EPSG:4326", *src.bounds, densify_pts=21)
                ]
            record["raster_status"] = "readable"
    except Exception as exc:
        record["raster_status"] = "unreadable"
        record["error"] = str(exc)
    return record


def site_config(site: AuditSite, half_size_m: float, worldcover_path: str, output_root: str) -> RunConfig:
    return RunConfig(
        site_name=f"worldcover_audit_{site.name}",
        site_name_cn=site.name,
        center_lat=site.lat,
        center_lon=site.lon,
        half_size_m=half_size_m,
        voxel_size_m=1.0,
        esa_worldcover_path=worldcover_path,
        output_root=output_root,
    )


def audit_sites(sites: list[AuditSite], half_size_m: float, worldcover_path: str, output_root: str) -> dict[str, Any]:
    from plan_worldcover_tiles import ManifestSite, plan_worldcover_tiles

    base_config = RunConfig(
        site_name="worldcover_coverage_audit",
        site_name_cn="worldcover_coverage_audit",
        half_size_m=half_size_m,
        voxel_size_m=1.0,
        esa_worldcover_path=worldcover_path,
        output_root=output_root,
    )
    dirs = ensure_dirs(base_config)
    candidates = discover_esa_worldcover_candidates(base_config, dirs)
    candidate_records = [candidate_record(path) for path in candidates]
    tile_plan = plan_worldcover_tiles(
        [ManifestSite(site.name, site.lat, site.lon, half_size_m) for site in sites],
        worldcover_path,
        output_root,
    )

    site_reports: list[dict[str, Any]] = []
    for site in tile_plan.get("sites", []):
        missing_for_site = [
            tile["tile_name"]
            for tile in site.get("tiles", [])
            if tile.get("status") in {"missing", "present_incomplete_or_wrong_size"}
        ]
        incomplete_for_site = [
            tile["tile_name"] for tile in site.get("tiles", []) if tile.get("status") == "present_incomplete_or_wrong_size"
        ]
        site_reports.append(
            {
                "site_name": site.get("site_name"),
                "lat": site.get("lat"),
                "lon": site.get("lon"),
                "half_size_m": site.get("half_size_m"),
                "coverage_status": site.get("coverage_status"),
                "expected_tiles": site.get("expected_tiles"),
                "missing_expected_tiles": missing_for_site,
                "incomplete_expected_tiles": incomplete_for_site,
                "selected_path": site.get("selected_path"),
                "selection_status": site.get("selection_status"),
                "candidate_count": len(candidates),
                "tile_statuses": {
                    tile["tile_name"]: tile.get("status") for tile in site.get("tiles", []) if tile.get("tile_name")
                },
            }
        )

    result = {
        "status": tile_plan.get("status"),
        "output_json": str(dirs["logs"] / "worldcover_coverage_audit.json"),
        "candidate_count": len(candidates),
        "covered_site_count": tile_plan.get("covered_site_count"),
        "missing_site_count": tile_plan.get("missing_site_count"),
        "missing_expected_tiles": tile_plan.get("missing_expected_tiles", []),
        "sites": site_reports,
        "candidates": candidate_records,
        "tile_manifest_json": tile_plan.get("output_json"),
    }
    write_json(dirs["logs"] / "worldcover_coverage_audit.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit local ESA WorldCover GeoTIFF coverage for target sites.")
    parser.add_argument("--site", action="append", type=parse_site, help="Site as name,lat,lon. Can be repeated.")
    parser.add_argument("--half-size-m", type=float, default=250.0, help="AOI half size used for expected tile lookup.")
    parser.add_argument("--worldcover-path", default="", help="Explicit WorldCover GeoTIFF path to audit.")
    parser.add_argument("--output-root", default="", help="Pipeline output root for the audit JSON.")
    args = parser.parse_args()

    sites = args.site if args.site else DEFAULT_SITES
    result = audit_sites(sites, args.half_size_m, args.worldcover_path, args.output_root)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
