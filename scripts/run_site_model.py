from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
if str(PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from china_voxel_pipeline import RunConfig, run_pipeline
from qa_site_output import qa_site_output
from render_voxel_review import render as render_voxel_review
from urban_morphology.workflow import run_full_workflow


PI = math.pi
GCJ_A = 6_378_245.0
GCJ_EE = 0.00669342162296594323


@dataclass(frozen=True)
class SiteModelRequest:
    site_name: str
    site_name_cn: str
    input_lat: float
    input_lon: float
    input_crs: str
    center_lat_wgs84: float
    center_lon_wgs84: float
    half_size_m: float
    voxel_size_m: float
    output_root: str


def _out_of_china(lon: float, lat: float) -> bool:
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _transform_lat(x: float, y: float) -> float:
    ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(y * PI) + 40.0 * math.sin(y / 3.0 * PI)) * 2.0 / 3.0
    ret += (160.0 * math.sin(y / 12.0 * PI) + 320 * math.sin(y * PI / 30.0)) * 2.0 / 3.0
    return ret


def _transform_lon(x: float, y: float) -> float:
    ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    ret += (20.0 * math.sin(6.0 * x * PI) + 20.0 * math.sin(2.0 * x * PI)) * 2.0 / 3.0
    ret += (20.0 * math.sin(x * PI) + 40.0 * math.sin(x / 3.0 * PI)) * 2.0 / 3.0
    ret += (150.0 * math.sin(x / 12.0 * PI) + 300.0 * math.sin(x / 30.0 * PI)) * 2.0 / 3.0
    return ret


def gcj02_to_wgs84(lon: float, lat: float) -> tuple[float, float]:
    if _out_of_china(lon, lat):
        return lon, lat
    dlat = _transform_lat(lon - 105.0, lat - 35.0)
    dlon = _transform_lon(lon - 105.0, lat - 35.0)
    radlat = lat / 180.0 * PI
    magic = math.sin(radlat)
    magic = 1 - GCJ_EE * magic * magic
    sqrtmagic = math.sqrt(magic)
    dlat = (dlat * 180.0) / ((GCJ_A * (1 - GCJ_EE)) / (magic * sqrtmagic) * PI)
    dlon = (dlon * 180.0) / (GCJ_A / sqrtmagic * math.cos(radlat) * PI)
    mglat = lat + dlat
    mglon = lon + dlon
    return lon * 2 - mglon, lat * 2 - mglat


def to_wgs84(lon: float, lat: float, input_crs: str) -> tuple[float, float]:
    crs = input_crs.strip().upper()
    if crs in {"WGS84", "EPSG:4326"}:
        return lon, lat
    if crs in {"GCJ02", "GCJ-02", "AMAP", "GAODE"}:
        return gcj02_to_wgs84(lon, lat)
    raise ValueError(f"Unsupported input CRS '{input_crs}'. Use WGS84 or GCJ02.")


def build_request(args: argparse.Namespace) -> SiteModelRequest:
    if not math.isfinite(args.lat) or not math.isfinite(args.lon):
        raise ValueError("Latitude and longitude must be finite numbers.")
    if not -90.0 <= args.lat <= 90.0:
        raise ValueError(f"Latitude is outside the valid range [-90, 90]: {args.lat}")
    if not -180.0 <= args.lon <= 180.0:
        raise ValueError(f"Longitude is outside the valid range [-180, 180]: {args.lon}")
    if not math.isfinite(args.half_size_m) or args.half_size_m <= 0:
        raise ValueError(f"half_size_m must be a positive finite number: {args.half_size_m}")
    if not math.isfinite(args.voxel_size_m) or args.voxel_size_m <= 0:
        raise ValueError(f"voxel_size_m must be a positive finite number: {args.voxel_size_m}")
    lon_wgs, lat_wgs = to_wgs84(args.lon, args.lat, args.input_crs)
    if _out_of_china(lon_wgs, lat_wgs):
        raise ValueError(
            "Normalized WGS84 coordinate is outside the supported China bounds: "
            f"lat={lat_wgs}, lon={lon_wgs}"
        )
    output_root = Path(args.output_root) if args.output_root else PROJECT_ROOT / "outputs_citylbm_voxel_china" / args.site_name
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    return SiteModelRequest(
        site_name=args.site_name,
        site_name_cn=args.site_name_cn,
        input_lat=args.lat,
        input_lon=args.lon,
        input_crs=args.input_crs,
        center_lat_wgs84=lat_wgs,
        center_lon_wgs84=lon_wgs,
        half_size_m=args.half_size_m,
        voxel_size_m=args.voxel_size_m,
        output_root=str(output_root),
    )


def find_rhino_layers_csv(output_root: Path) -> Path:
    candidates = sorted((output_root / "05_rhino").glob("final_city_voxel_*_layers.csv"), key=lambda path: path.stat().st_mtime)
    if candidates:
        return candidates[-1]
    return output_root / "05_rhino" / "final_city_voxel_0p1m_layers.csv"


def render_review_image(output_root: Path, title: str) -> Path:
    image_path = output_root / "10_figures" / f"{output_root.name}_voxel_model_review.png"
    render_args = argparse.Namespace(
        terrain=output_root / "02_gis" / "terrain_mesh.csv",
        voxels=output_root / "04_voxels" / "sparse_voxels.csv",
        layers=find_rhino_layers_csv(output_root),
        output=image_path,
        title=title,
    )
    render_voxel_review(render_args)
    return image_path


def readiness_args_from_request(
    request: SiteModelRequest,
    worldcover_path: str = "",
    allow_no_osm_core_features: bool = False,
) -> argparse.Namespace:
    return argparse.Namespace(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        lat=request.center_lat_wgs84,
        lon=request.center_lon_wgs84,
        input_crs="WGS84",
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        output_root=request.output_root,
        worldcover_path=worldcover_path,
        worldcover_bounds_tolerance_deg=1e-6,
        dem_min_bytes=1024,
        dem_max_abs_elevation_m=9000.0,
        dem_timeout_s=10,
        osm_timeout_s=10,
        allow_no_osm_core_features=allow_no_osm_core_features,
        strict=True,
    )


def run_readiness_gate(
    request: SiteModelRequest,
    worldcover_path: str = "",
    allow_no_osm_core_features: bool = False,
) -> dict[str, Any]:
    from real_data_readiness_report import build_readiness_report

    report = build_readiness_report(
        readiness_args_from_request(
            request,
            worldcover_path=worldcover_path,
            allow_no_osm_core_features=allow_no_osm_core_features,
        )
    )
    if report.get("status") != "ready":
        report_path = report.get("outputs", {}).get("report_json") or Path(request.output_root) / "12_logs" / "real_data_readiness_report.json"
        failed = ", ".join(report.get("failed_components", [])) or "unknown"
        raise RuntimeError(f"Real-data readiness failed before modeling ({failed}). See {report_path}")
    return report


def run_site_model(
    request: SiteModelRequest,
    run_morphology: bool = True,
    render_image: bool = True,
    run_qa: bool = True,
    qa_min_buildings: int = 1,
    allow_fallback_preview: bool = False,
    check_readiness: bool = True,
    readiness_worldcover_path: str = "",
    allow_no_osm_core_features: bool = False,
    rhino_export_mode: str = "component_mesh_groups",
    roadside_tree_spacing_m: float = 10.0,
    roadside_tree_offset_m: float = 2.0,
    roadside_tree_intersection_clearance_m: float = 8.0,
) -> dict[str, Any]:
    output_root = Path(request.output_root)
    config = RunConfig(
        site_name=request.site_name,
        site_name_cn=request.site_name_cn,
        center_lat=request.center_lat_wgs84,
        center_lon=request.center_lon_wgs84,
        half_size_m=request.half_size_m,
        voxel_size_m=request.voxel_size_m,
        rhino_export_mode=rhino_export_mode,
        roadside_tree_spacing_m=roadside_tree_spacing_m,
        roadside_tree_offset_m=roadside_tree_offset_m,
        roadside_tree_intersection_clearance_m=roadside_tree_intersection_clearance_m,
        output_root=str(output_root),
        strict_real_data=not allow_fallback_preview,
    )
    request_path = output_root / "12_logs" / "site_model_request.json"
    request_path.parent.mkdir(parents=True, exist_ok=True)
    request_path.write_text(json.dumps(asdict(request), ensure_ascii=True, indent=2), encoding="utf-8")

    readiness_report = None
    if check_readiness and not allow_fallback_preview:
        readiness_report = run_readiness_gate(
            request,
            worldcover_path=readiness_worldcover_path,
            allow_no_osm_core_features=allow_no_osm_core_features,
        )

    pipeline_report = run_pipeline(config)
    morphology_report = run_full_workflow(project_root=PROJECT_ROOT, output_root=output_root) if run_morphology else None
    preview_path = render_review_image(output_root, f"{request.site_name_cn} {request.half_size_m * 2:.0f}m {request.voxel_size_m:g}m voxel model") if render_image else None
    summary_path = output_root / "12_logs" / "site_model_summary.json"
    summary = {
        "status": "success",
        "request": asdict(request),
        "rhino_file": pipeline_report.get("rhino_meta", {}).get("file"),
        "pipeline_scene_classification": pipeline_report.get("scene_classification", {}).get("classification", {}),
        "artifact_count": pipeline_report.get("artifact_count"),
        "strict_real_data": bool(config.strict_real_data),
        "allow_fallback_preview": bool(allow_fallback_preview),
        "rhino_export_mode": config.rhino_export_mode,
        "roadside_tree_parameters": {
            "spacing_m": config.roadside_tree_spacing_m,
            "offset_from_road_edge_m": config.roadside_tree_offset_m,
            "intersection_clearance_m": config.roadside_tree_intersection_clearance_m,
            "merge_distance_m": config.roadside_tree_merge_distance_m,
        },
        "readiness_check": {
            "enabled": bool(check_readiness and not allow_fallback_preview),
            "status": (readiness_report or {}).get("status"),
            "component_results": (readiness_report or {}).get("component_results"),
            "report_json": (readiness_report or {}).get("outputs", {}).get("report_json"),
        },
        "real_data_source_check": pipeline_report.get("real_data_source_check"),
        "morphology_quality_status": (morphology_report or {}).get("quality_control", {}).get("status"),
        "site_output_qa_status": None,
        "site_output_qa_errors": None,
        "site_output_qa_warnings": None,
        "site_output_qa_optional_missing": None,
        "preview_image": str(preview_path) if preview_path else None,
    }
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    qa_report = (
        qa_site_output(
            output_root,
            min_buildings=qa_min_buildings,
            expected_lat=request.center_lat_wgs84,
            expected_lon=request.center_lon_wgs84,
            expected_aoi_width_m=request.half_size_m * 2.0,
            expected_voxel_size_m=request.voxel_size_m,
            require_real_data_sources=not allow_fallback_preview,
            require_readiness_check=bool(check_readiness and not allow_fallback_preview),
            require_preview_image=render_image,
        )
        if run_qa and run_morphology
        else None
    )
    summary["site_output_qa_status"] = (qa_report or {}).get("status")
    summary["site_output_qa_errors"] = (qa_report or {}).get("errors")
    summary["site_output_qa_warnings"] = (qa_report or {}).get("warnings")
    summary["site_output_qa_optional_missing"] = (qa_report or {}).get("optional_missing")
    summary_path.write_text(json.dumps(summary, ensure_ascii=True, indent=2), encoding="utf-8")
    if qa_report and qa_report.get("status") != "passed":
        raise RuntimeError(f"Site output QA failed. See {output_root / '12_logs' / 'site_output_qa.json'}")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full VoxCity/urbanbase site modeling workflow for one AOI.")
    parser.add_argument("--site-name", required=True, help="ASCII-safe output folder and site id.")
    parser.add_argument("--site-name-cn", required=True, help="Human-readable Chinese site name.")
    parser.add_argument("--lat", type=float, required=True, help="Input latitude.")
    parser.add_argument("--lon", type=float, required=True, help="Input longitude.")
    parser.add_argument("--input-crs", default="WGS84", choices=["WGS84", "EPSG:4326", "GCJ02", "GCJ-02", "AMAP", "GAODE"])
    parser.add_argument("--half-size-m", type=float, default=250.0)
    parser.add_argument("--voxel-size-m", type=float, default=1.0)
    parser.add_argument(
        "--rhino-export-mode",
        default="component_mesh_groups",
        choices=["mesh", "building_voxel_groups", "component_mesh_groups"],
    )
    parser.add_argument("--roadside-tree-spacing-m", type=float, default=10.0)
    parser.add_argument("--roadside-tree-offset-m", type=float, default=2.0)
    parser.add_argument("--roadside-tree-intersection-clearance-m", type=float, default=8.0)
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--worldcover-path", default="", help="Optional explicit ESA WorldCover GeoTIFF path for readiness checks.")
    parser.add_argument("--skip-morphology", action="store_true")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument("--skip-qa", action="store_true")
    parser.add_argument("--qa-min-buildings", type=int, default=1)
    parser.add_argument("--skip-readiness-check", action="store_true", help="Skip the formal real-data readiness gate before modeling.")
    parser.add_argument(
        "--allow-no-osm-core-features",
        action="store_true",
        help="Allow a real, non-fallback OSM cache with no building/highway ways for natural or water-focused AOIs.",
    )
    parser.add_argument(
        "--allow-fallback-preview",
        action="store_true",
        help="Allow DEM/WorldCover/OSM fallback output for preview/debugging only. Formal runs are strict by default.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print normalized site request without running modeling.")
    args = parser.parse_args()
    request = build_request(args)
    print(json.dumps({"request": asdict(request)}, ensure_ascii=False, indent=2))
    if args.dry_run:
        return
    summary = run_site_model(
        request,
        run_morphology=not args.skip_morphology,
        render_image=not args.skip_render,
        run_qa=not args.skip_qa,
        qa_min_buildings=args.qa_min_buildings,
        allow_fallback_preview=args.allow_fallback_preview,
        check_readiness=not args.skip_readiness_check,
        readiness_worldcover_path=args.worldcover_path,
        allow_no_osm_core_features=args.allow_no_osm_core_features,
        rhino_export_mode=args.rhino_export_mode,
        roadside_tree_spacing_m=args.roadside_tree_spacing_m,
        roadside_tree_offset_m=args.roadside_tree_offset_m,
        roadside_tree_intersection_clearance_m=args.roadside_tree_intersection_clearance_m,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
