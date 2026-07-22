from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from china_voxel_pipeline import RunConfig, rhino_output_base, run_pipeline, safe_filename  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the VoxCity all-element voxel pipeline for one WGS84 coordinate.")
    parser.add_argument("--lat", type=float, required=True, help="Center latitude in WGS84.")
    parser.add_argument("--lon", type=float, required=True, help="Center longitude in WGS84.")
    parser.add_argument("--site-name", required=True, help="ASCII site id used for cache and output names.")
    parser.add_argument("--site-name-cn", default="", help="Human-readable Chinese site name.")
    parser.add_argument("--half-size-m", type=float, default=250.0, help="Half size of the square AOI in meters.")
    parser.add_argument("--voxel-size-m", type=float, default=1.0, help="Sparse voxel grid size in meters.")
    parser.add_argument(
        "--rhino-export-mode",
        default="component_mesh_groups",
        choices=["mesh", "building_voxel_groups", "component_mesh_groups"],
        help="Rhino geometry organization mode.",
    )
    parser.add_argument("--roadside-tree-spacing-m", type=float, default=10.0, help="Derived street-tree spacing along road centerlines.")
    parser.add_argument("--roadside-tree-offset-m", type=float, default=2.0, help="Derived street-tree offset from estimated road edge.")
    parser.add_argument("--roadside-tree-intersection-clearance-m", type=float, default=8.0, help="No derived street trees within this distance from road junctions/endpoints.")
    parser.add_argument("--output-root", default="", help="Output root. Defaults to outputs_citylbm_voxel_china/<site-name>.")
    parser.add_argument("--worldcover-path", default="", help="Optional ESA WorldCover GeoTIFF path.")
    parser.add_argument("--allow-fallback-preview", action="store_true", help="Allow synthetic/empty fallbacks for preview runs.")
    args = parser.parse_args()

    site_slug = safe_filename(args.site_name)
    output_root = args.output_root or str(PROJECT_ROOT / "outputs_citylbm_voxel_china" / site_slug)
    config = RunConfig(
        site_name=site_slug,
        site_name_cn=args.site_name_cn or site_slug,
        center_lat=args.lat,
        center_lon=args.lon,
        half_size_m=args.half_size_m,
        voxel_size_m=args.voxel_size_m,
        rhino_export_mode=args.rhino_export_mode,
        roadside_tree_spacing_m=args.roadside_tree_spacing_m,
        roadside_tree_offset_m=args.roadside_tree_offset_m,
        roadside_tree_intersection_clearance_m=args.roadside_tree_intersection_clearance_m,
        output_root=output_root,
        esa_worldcover_path=args.worldcover_path,
        strict_real_data=not args.allow_fallback_preview,
    )
    report = run_pipeline(config)

    out = Path(output_root)
    screenshot = out / "10_figures" / f"{site_slug}_voxel_model_review.png"
    render_script = PROJECT_ROOT / "scripts" / "render_voxel_review.py"
    subprocess.check_call([
        sys.executable,
        str(render_script),
        "--terrain",
        str(out / "02_gis" / "terrain_mesh.csv"),
        "--voxels",
        str(out / "04_voxels" / "sparse_voxels.csv"),
        "--layers",
        str(out / "05_rhino" / f"{rhino_output_base(config)}_layers.csv"),
        "--output",
        str(screenshot),
        "--title",
        f"{config.site_name_cn} {config.half_size_m * 2:.0f} m Voxel Model Review",
    ])

    summary = {
        "status": "success",
        "finished_at": report.get("finished_at"),
        "output_root": str(out),
        "rhino": report.get("rhino_meta", {}).get("file"),
        "screenshot": str(screenshot),
        "scene_classification": report.get("scene_classification", {}).get("classification", {}),
        "artifact_count": report.get("artifact_count"),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
