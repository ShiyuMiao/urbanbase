from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from qa_site_output import qa_site_output
from run_site_model import SiteModelRequest, run_site_model, to_wgs84


DLUT_ARCH_ART_GCJ02_LAT = 38.881098
DLUT_ARCH_ART_GCJ02_LON = 121.526615


def default_output_root() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return PROJECT_ROOT / "outputs_citylbm_voxel_china" / f"_smoke_tiny_e2e_{stamp}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a clean-directory tiny end-to-end site modeling smoke test.")
    parser.add_argument("--output-root", default=None)
    parser.add_argument("--half-size-m", type=float, default=20.0)
    parser.add_argument("--voxel-size-m", type=float, default=2.0)
    parser.add_argument("--skip-render", action="store_true")
    args = parser.parse_args()

    lon_wgs, lat_wgs = to_wgs84(DLUT_ARCH_ART_GCJ02_LON, DLUT_ARCH_ART_GCJ02_LAT, "GCJ02")
    output_root = Path(args.output_root) if args.output_root else default_output_root()
    if not output_root.is_absolute():
        output_root = PROJECT_ROOT / output_root
    if output_root.exists() and any(output_root.iterdir()):
        raise SystemExit(f"Refusing to run tiny E2E smoke test in non-empty directory: {output_root}")

    request = SiteModelRequest(
        site_name=output_root.name,
        site_name_cn="DUT Architecture and Art College tiny E2E smoke",
        input_lat=DLUT_ARCH_ART_GCJ02_LAT,
        input_lon=DLUT_ARCH_ART_GCJ02_LON,
        input_crs="GCJ02",
        center_lat_wgs84=lat_wgs,
        center_lon_wgs84=lon_wgs,
        half_size_m=args.half_size_m,
        voxel_size_m=args.voxel_size_m,
        output_root=str(output_root),
    )
    summary = run_site_model(
        request,
        run_morphology=True,
        render_image=not args.skip_render,
        run_qa=True,
        qa_min_buildings=0,
        allow_fallback_preview=True,
    )
    qa = qa_site_output(
        output_root,
        min_buildings=0,
        expected_lat=lat_wgs,
        expected_lon=lon_wgs,
        expected_aoi_width_m=args.half_size_m * 2.0,
        expected_voxel_size_m=args.voxel_size_m,
        require_preview_image=not args.skip_render,
    )
    if qa["status"] != "passed":
        raise SystemExit(f"Tiny E2E QA failed: {qa['errors']}")
    voxel_slug = f"{args.voxel_size_m:g}".replace(".", "p") + "m"
    expected_rhino = output_root / "05_rhino" / f"final_city_voxel_{voxel_slug}.3dm"
    if not expected_rhino.exists():
        raise SystemExit(f"Tiny E2E did not write the voxel-size-specific Rhino file: {expected_rhino}")
    expected_layers = {
        f"01_Buildings_{voxel_slug}_Voxels",
        f"01a_Building_Bases_{voxel_slug}_Voxels",
        f"02_Roads_Hardscape_{voxel_slug}_Voxels",
        "02a_Road_Centerlines_Vector",
        f"03_Water_{voxel_slug}_Voxels",
        f"04_Green_Trees_{voxel_slug}_Voxels",
        f"05_Green_Grass_{voxel_slug}_Voxels",
        f"06_Terrain_DEM_{voxel_slug}_Voxels",
        "09_Geographic_Coordinate_Info",
    }
    layer_csv = output_root / "05_rhino" / f"final_city_voxel_{voxel_slug}_layers.csv"
    layer_text = layer_csv.read_text(encoding="utf-8-sig") if layer_csv.exists() else ""
    missing_layers = sorted(layer for layer in expected_layers if layer not in layer_text)
    if missing_layers:
        raise SystemExit(f"Tiny E2E Rhino layer names do not match voxel size {args.voxel_size_m:g} m: {missing_layers}")
    result = {
        "status": "success",
        "request": asdict(request),
        "summary": summary,
        "qa": {
            "status": qa["status"],
            "warnings": qa["warnings"],
            "optional_missing": qa["optional_missing"],
            "rhino_summary": qa["rhino_summary"],
            "preview_image_summary": qa["preview_image_summary"],
            "table_rows": qa["table_rows"],
            "table_schema_summary": qa["table_schema_summary"],
            "table_value_summary": qa["table_value_summary"],
            "site_consistency": qa["site_consistency"],
        },
        "expected_rhino": str(expected_rhino),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
