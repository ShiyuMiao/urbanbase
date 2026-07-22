from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = PROJECT_ROOT / "scripts"
SRC = PROJECT_ROOT / "src"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import run_site_model as site_runner
from china_voxel_pipeline import RunConfig, build_sparse_runs, ensure_dirs, export_rhino, voxel_layer_names
from qa_site_output import LCZ_REQUIRED_COLUMNS, MORPHOLOGY_REQUIRED_COLUMNS, RISK_REQUIRED_COLUMNS, TYPICAL_BLOCK_REQUIRED_COLUMNS, qa_site_output
from run_site_model import build_request, to_wgs84


DLUT_ARCH_ART_GCJ02_LAT = 38.881098
DLUT_ARCH_ART_GCJ02_LON = 121.526615
DLUT_ARCH_ART_WGS84_LAT = 38.88024056122594
DLUT_ARCH_ART_WGS84_LON = 121.52153023152763


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _assert_close(observed: float, expected: float, tolerance: float, label: str) -> None:
    if abs(observed - expected) > tolerance:
        raise AssertionError(f"{label} {observed} differs from expected {expected} by more than {tolerance}")


def _voxel_size_slug(voxel_size_m: float) -> str:
    text = f"{float(voxel_size_m):g}".replace("-", "m")
    return f"{text.replace('.', 'p')}m"


def _rhino_base(voxel_size_m: float) -> str:
    return f"final_city_voxel_{_voxel_size_slug(voxel_size_m)}"


def _write_minimal_rhino(path: Path, voxel_size_m: float) -> None:
    import rhino3dm

    suffix = _voxel_size_slug(voxel_size_m)
    layer_names = [
        "00_AOI_Boundary",
        f"01_Buildings_{suffix}_Voxels",
        f"01a_Building_Bases_{suffix}_Voxels",
        f"02_Roads_Hardscape_{suffix}_Voxels",
        "02a_Road_Centerlines_Vector",
        f"03_Water_{suffix}_Voxels",
        f"04_Green_Trees_{suffix}_Voxels",
        f"05_Green_Grass_{suffix}_Voxels",
        f"06_Terrain_DEM_{suffix}_Voxels",
        "07_POI_Function_Labels",
        "08_LCZ_Morphology_Info_Text",
        "09_Geographic_Coordinate_Info",
    ]
    model = rhino3dm.File3dm()
    for name in layer_names:
        layer = rhino3dm.Layer()
        layer.Name = name
        layer.Color = (120, 120, 120, 255)
        model.Layers.Add(layer)
    for idx, layer_index in enumerate([0, 1, 8]):
        attributes = rhino3dm.ObjectAttributes()
        attributes.LayerIndex = layer_index
        model.Objects.AddPoint(rhino3dm.Point3d(float(idx), 0.0, 0.0), attributes)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not model.Write(str(path), 7):
        raise AssertionError(f"Failed to write minimal Rhino fixture: {path}")


def _write_minimal_png(path: Path) -> None:
    from PIL import Image, ImageDraw

    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (32, 24), (245, 245, 245))
    draw = ImageDraw.Draw(image)
    draw.rectangle((4, 6, 14, 18), fill=(196, 40, 27))
    draw.rectangle((16, 10, 28, 20), fill=(76, 140, 84))
    image.save(path, format="PNG")


def _morphology_columns() -> list[str]:
    ordered: list[str] = []
    for columns in MORPHOLOGY_REQUIRED_COLUMNS.values():
        for column in sorted(columns):
            if column not in ordered:
                ordered.append(column)
    return ordered


def _row_for_columns(columns: list[str]) -> dict[str, object]:
    row: dict[str, object] = {column: 0 for column in columns}
    row.update(
        {
            "grid_id": "cell_0",
            "row": 0,
            "col": 0,
            "grid_size_m": 250.0,
            "area_m2": 62500.0,
            "center_lon": DLUT_ARCH_ART_WGS84_LON,
            "center_lat": DLUT_ARCH_ART_WGS84_LAT,
            "data_source_buildings": "fixture",
            "data_source_green": "fixture",
            "data_source_terrain": "fixture",
            "source_quality_flag": "fixture",
            "building_count": 2,
            "building_footprint_area_m2": 1000.0,
            "building_coverage_ratio": 0.016,
            "building_height_mean_m": 12.0,
            "building_height_max_m": 18.0,
            "building_floor_area_est_m2": 3000.0,
            "floor_area_ratio_est": 0.048,
            "open_space_ratio": 0.95,
            "green_area_m2": 5000.0,
            "green_ratio": 0.08,
            "tree_cover_area_m2": 2000.0,
            "tree_cover_ratio": 0.032,
            "grass_area_m2": 3000.0,
            "grass_ratio": 0.048,
            "terrain_elevation_mean_m": 20.0,
            "terrain_elevation_min_m": 19.0,
            "terrain_elevation_max_m": 21.0,
            "terrain_relief_m": 2.0,
            "lcz_rule": "LCZ 6",
            "lcz_rule_confidence": 0.62,
            "lcz_rule_reasons": "fixture",
            "lcz_probability_top1": "LCZ 6",
            "lcz_probability_top2": "LCZ 9",
            "lcz_top1_probability": 0.62,
            "lcz_top2_probability": 0.24,
            "lcz_top1_top2_margin": 0.38,
            "lcz_entropy": 0.9,
            "lcz_entropy_norm": 0.4,
            "lcz_confidence_level": "medium",
            "lcz_distance_top1": 0.2,
            "heat_risk_score": 0.4,
            "heat_risk_level": "medium",
            "low_ventilation_risk_score": 0.3,
            "low_ventilation_risk_level": "low",
            "exposure_score": 0.35,
            "exposure_level": "medium",
            "heat_wind_compound_risk_score": 0.36,
            "heat_wind_compound_risk_level": "medium",
            "risk_data_sources": "fixture",
            "risk_quality_flags": "fixture",
            "selection_score": 0.8,
            "risk_rank": 1,
        }
    )
    return row


def _write_one_row_csv(path: Path, columns: list[str]) -> None:
    row = _row_for_columns(columns)
    lines = [",".join(columns), ",".join(str(row[column]) for column in columns)]
    _write_text(path, "\n".join(lines) + "\n")


def _write_minimal_research_tables(root: Path) -> None:
    morphology_columns = _morphology_columns()
    lcz_columns = morphology_columns + sorted(LCZ_REQUIRED_COLUMNS)
    risk_columns = lcz_columns + sorted(RISK_REQUIRED_COLUMNS)
    typical_columns = risk_columns + sorted(TYPICAL_BLOCK_REQUIRED_COLUMNS)
    _write_one_row_csv(root / "08_morphology" / "morphology_indicators_250m.csv", morphology_columns)
    _write_one_row_csv(root / "09_lcz" / "lcz_classification_250m.csv", lcz_columns)
    _write_one_row_csv(root / "14_heat_wind_risk" / "heat_wind_compound_risk_250m.csv", risk_columns)
    _write_one_row_csv(root / "15_typical_blocks" / "typical_blocks_for_citylbm.csv", typical_columns)


def make_minimal_site_bundle(root: Path, voxel_size_m: float = 0.1) -> None:
    rhino_base = _rhino_base(voxel_size_m)
    _write_json(
        root / "02_gis" / "origin_mapping.json",
        {
            "origin_lon": DLUT_ARCH_ART_WGS84_LON,
            "origin_lat": DLUT_ARCH_ART_WGS84_LAT,
            "origin_elevation": 14.2,
            "unit": "meter",
            "projected_crs": "local tangent-plane meters around WGS84 AOI centroid",
        },
    )
    _write_json(
        root / "04_voxels" / "voxel_grid_config.json",
        {
            "voxel_size_m": voxel_size_m,
            "aoi_width_m": 500.0,
            "aoi_height_m": 500.0,
            "vertical_extent_m": 80.0,
            "nx": int(500.0 / voxel_size_m),
            "ny": int(500.0 / voxel_size_m),
            "nz": int(80.0 / voxel_size_m),
            "representation": "sparse run-length voxel cuboids",
        },
    )
    _write_minimal_rhino(root / "05_rhino" / f"{rhino_base}.3dm", voxel_size_m)
    _write_json(
        root / "05_rhino" / f"{rhino_base}_metadata.json",
        {
            "file": f"05_rhino/{rhino_base}.3dm",
            "object_count": 3,
            "layer_count": 12,
            "total_sparse_runs": 5,
            "total_voxels_represented": 100,
            "voxel_size_m": voxel_size_m,
            "layer_voxel_counts": {
                f"01_Buildings_{_voxel_size_slug(voxel_size_m)}_Voxels": 80,
                f"06_Terrain_DEM_{_voxel_size_slug(voxel_size_m)}_Voxels": 20,
            },
        },
    )
    _write_text(
        root / "05_rhino" / f"{rhino_base}_layers.csv",
        "\n".join(
            [
                "layer,r,g,b,a,unit",
                "00_AOI_Boundary,255,220,80,255,meter",
                f"01_Buildings_{_voxel_size_slug(voxel_size_m)}_Voxels,196,40,27,255,meter",
                f"01a_Building_Bases_{_voxel_size_slug(voxel_size_m)}_Voxels,118,67,46,255,meter",
                "02a_Road_Centerlines_Vector,250,235,95,255,meter",
                f"06_Terrain_DEM_{_voxel_size_slug(voxel_size_m)}_Voxels,165,155,143,255,meter",
                "08_LCZ_Morphology_Info_Text,35,35,35,255,meter",
                "09_Geographic_Coordinate_Info,28,93,153,255,meter",
            ]
        )
        + "\n",
    )
    _write_text(root / "04_voxels" / "sparse_voxels.csv", f"layer,voxel_count,voxel_size_m\nbuilding,100,{voxel_size_m}\n")
    _write_text(
        root / "06_tables" / "basic_site_statistics.csv",
        "\n".join(
            [
                "category,metric,value",
                "features,building_count,2",
                "dem,elevation_range_m,1.5",
            ]
        )
        + "\n",
    )
    _write_json(root / "07_audit" / "morphology_lcz_risk_quality_report.json", {"status": "passed", "hard_errors": []})
    _write_minimal_research_tables(root)
    _write_json(
        root / "12_logs" / "run_report.json",
        {
            "config": {
                "site_name": "minimal_site",
                "center_lat": DLUT_ARCH_ART_WGS84_LAT,
                "center_lon": DLUT_ARCH_ART_WGS84_LON,
                "half_size_m": 250.0,
                "voxel_size_m": voxel_size_m,
            }
        },
    )
    _write_minimal_png(root / "10_figures" / "minimal_site_voxel_model_review.png")


def write_ready_site_summary(root: Path) -> None:
    _write_json(
        root / "12_logs" / "site_model_summary.json",
        {
            "status": "success",
            "strict_real_data": True,
            "allow_fallback_preview": False,
            "readiness_check": {
                "enabled": True,
                "status": "ready",
                "component_results": {
                    "preflight": "passed",
                    "worldcover": "passed",
                    "dem": "passed",
                    "osm": "passed",
                },
                "report_json": str(root / "12_logs" / "real_data_readiness_report.json"),
            },
        },
    )


def test_coordinate_normalization() -> dict:
    lon, lat = to_wgs84(DLUT_ARCH_ART_GCJ02_LON, DLUT_ARCH_ART_GCJ02_LAT, "GCJ02")
    _assert_close(lat, DLUT_ARCH_ART_WGS84_LAT, 1e-9, "GCJ02->WGS84 latitude")
    _assert_close(lon, DLUT_ARCH_ART_WGS84_LON, 1e-9, "GCJ02->WGS84 longitude")

    lon_wgs, lat_wgs = to_wgs84(DLUT_ARCH_ART_WGS84_LON, DLUT_ARCH_ART_WGS84_LAT, "WGS84")
    _assert_close(lat_wgs, DLUT_ARCH_ART_WGS84_LAT, 0.0, "WGS84 latitude passthrough")
    _assert_close(lon_wgs, DLUT_ARCH_ART_WGS84_LON, 0.0, "WGS84 longitude passthrough")

    request = build_request(
        argparse.Namespace(
            site_name="dry_run_arch_art",
            site_name_cn="DUT Architecture and Art College dry run",
            lat=DLUT_ARCH_ART_GCJ02_LAT,
            lon=DLUT_ARCH_ART_GCJ02_LON,
            input_crs="GCJ02",
            half_size_m=250.0,
            voxel_size_m=0.1,
            output_root=None,
        )
    )
    _assert_close(request.center_lat_wgs84, DLUT_ARCH_ART_WGS84_LAT, 1e-9, "request center latitude")
    _assert_close(request.center_lon_wgs84, DLUT_ARCH_ART_WGS84_LON, 1e-9, "request center longitude")

    try:
        to_wgs84(DLUT_ARCH_ART_GCJ02_LON, DLUT_ARCH_ART_GCJ02_LAT, "BD09")
    except ValueError:
        unsupported_crs_rejected = True
    else:
        unsupported_crs_rejected = False
    if not unsupported_crs_rejected:
        raise AssertionError("Unsupported CRS should raise ValueError")

    return {"gcj02_to_wgs84": "passed", "wgs84_passthrough": "passed", "unsupported_crs": "rejected"}


def test_minimal_qa_bundle() -> dict:
    with tempfile.TemporaryDirectory(prefix="urbanbase_site_qa_") as tmp:
        root = Path(tmp) / "minimal_site"
        make_minimal_site_bundle(root)
        passed = qa_site_output(
            root,
            expected_lat=DLUT_ARCH_ART_WGS84_LAT,
            expected_lon=DLUT_ARCH_ART_WGS84_LON,
            expected_aoi_width_m=500.0,
            expected_voxel_size_m=0.1,
        )
        if passed["status"] != "passed":
            raise AssertionError(f"Minimal QA bundle should pass: {passed['errors']}")

        failed = qa_site_output(
            root,
            expected_lat=DLUT_ARCH_ART_WGS84_LAT + 0.01,
            expected_lon=DLUT_ARCH_ART_WGS84_LON,
            expected_aoi_width_m=500.0,
            expected_voxel_size_m=0.1,
        )
        if failed["status"] != "failed":
            raise AssertionError("QA should fail when expected latitude is wrong")
        if not any("origin_lat" in item for item in failed["errors"]):
            raise AssertionError(f"Wrong-coordinate QA failure did not mention origin_lat: {failed['errors']}")

        readiness_failed = qa_site_output(
            root,
            expected_lat=DLUT_ARCH_ART_WGS84_LAT,
            expected_lon=DLUT_ARCH_ART_WGS84_LON,
            expected_aoi_width_m=500.0,
            expected_voxel_size_m=0.1,
            require_readiness_check=True,
        )
        if readiness_failed["status"] != "failed":
            raise AssertionError("QA should fail when formal readiness is required but site summary is missing")
        if not any("Readiness" in item or "readiness" in item for item in readiness_failed["errors"]):
            raise AssertionError(f"Readiness QA failure did not mention readiness: {readiness_failed['errors']}")

        write_ready_site_summary(root)
        readiness_passed = qa_site_output(
            root,
            expected_lat=DLUT_ARCH_ART_WGS84_LAT,
            expected_lon=DLUT_ARCH_ART_WGS84_LON,
            expected_aoi_width_m=500.0,
            expected_voxel_size_m=0.1,
            require_readiness_check=True,
        )
        if readiness_passed["status"] != "passed":
            raise AssertionError(f"QA should pass with ready site summary: {readiness_passed['errors']}")
    return {"minimal_bundle_pass": "passed", "wrong_coordinate_failure": "passed", "readiness_gate_qa": "passed"}


def test_dynamic_rhino_name_qa_discovery() -> dict:
    with tempfile.TemporaryDirectory(prefix="urbanbase_site_qa_dynamic_") as tmp:
        root = Path(tmp) / "minimal_site_2m"
        make_minimal_site_bundle(root, voxel_size_m=2.0)
        passed = qa_site_output(
            root,
            expected_lat=DLUT_ARCH_ART_WGS84_LAT,
            expected_lon=DLUT_ARCH_ART_WGS84_LON,
            expected_aoi_width_m=500.0,
            expected_voxel_size_m=2.0,
        )
        if passed["status"] != "passed":
            raise AssertionError(f"Dynamic Rhino-name QA bundle should pass: {passed['errors']}")
        rhino_path = Path(passed["file_checks"]["rhino"]["path"])
        metadata_path = Path(passed["file_checks"]["rhino_metadata"]["path"])
        if rhino_path.name != "final_city_voxel_2m.3dm":
            raise AssertionError(f"QA selected wrong Rhino file for 2m voxels: {rhino_path}")
        if metadata_path.name != "final_city_voxel_2m_metadata.json":
            raise AssertionError(f"QA selected wrong Rhino metadata for 2m voxels: {metadata_path}")
    return {"dynamic_2m_rhino_discovery": "passed"}


def test_run_site_model_strict_real_data_default() -> dict:
    observed: list[bool] = []
    readiness_calls: list[str] = []
    original_run_pipeline = site_runner.run_pipeline
    original_run_readiness_gate = site_runner.run_readiness_gate
    try:
        def fake_run_pipeline(config):
            observed.append(bool(config.strict_real_data))
            return {
                "rhino_meta": {"file": "05_rhino/final_city_voxel_2m.3dm"},
                "scene_classification": {"classification": {}},
                "artifact_count": 0,
                "real_data_source_check": {
                    "status": "passed" if config.strict_real_data else "passed_with_warnings",
                    "checks": {"strict_real_data": bool(config.strict_real_data)},
                },
            }

        def fake_run_readiness_gate(request, worldcover_path="", allow_no_osm_core_features=False):
            readiness_calls.append(request.site_name)
            return {
                "status": "ready",
                "component_results": {"preflight": "passed", "worldcover": "passed", "dem": "passed", "osm": "passed"},
                "outputs": {"report_json": str(Path(request.output_root) / "12_logs" / "real_data_readiness_report.json")},
            }

        site_runner.run_pipeline = fake_run_pipeline
        site_runner.run_readiness_gate = fake_run_readiness_gate
        with tempfile.TemporaryDirectory(prefix="urbanbase_strict_flag_") as tmp:
            request = site_runner.SiteModelRequest(
                site_name="strict_flag_probe",
                site_name_cn="Strict flag probe",
                input_lat=DLUT_ARCH_ART_WGS84_LAT,
                input_lon=DLUT_ARCH_ART_WGS84_LON,
                input_crs="WGS84",
                center_lat_wgs84=DLUT_ARCH_ART_WGS84_LAT,
                center_lon_wgs84=DLUT_ARCH_ART_WGS84_LON,
                half_size_m=20.0,
                voxel_size_m=2.0,
                output_root=str(Path(tmp) / "strict_flag_probe"),
            )
            site_runner.run_site_model(request, run_morphology=False, render_image=False, run_qa=False)
            site_runner.run_site_model(
                request,
                run_morphology=False,
                render_image=False,
                run_qa=False,
                allow_fallback_preview=True,
            )
            site_runner.run_site_model(
                request,
                run_morphology=False,
                render_image=False,
                run_qa=False,
                check_readiness=False,
            )
    finally:
        site_runner.run_pipeline = original_run_pipeline
        site_runner.run_readiness_gate = original_run_readiness_gate
    if observed != [True, False, True]:
        raise AssertionError(f"run_site_model strict_real_data flags were not [True, False, True]: {observed}")
    if readiness_calls != ["strict_flag_probe"]:
        raise AssertionError(f"readiness gate should run only for the default formal call: {readiness_calls}")
    return {"default_strict": "passed", "preview_relaxes_strict": "passed", "readiness_gate_default": "passed"}


def test_building_anchor_and_road_centerline_export() -> dict:
    import geopandas as gpd
    import numpy as np
    from shapely.geometry import LineString, Polygon

    with tempfile.TemporaryDirectory(prefix="urbanbase_anchor_export_") as tmp:
        config = RunConfig(
            site_name="anchor_export_probe",
            site_name_cn="anchor export probe",
            half_size_m=10.0,
            voxel_size_m=2.0,
            vertical_extent_m=30.0,
            rhino_export_mode="building_voxel_groups",
            roadside_tree_spacing_m=6.0,
            roadside_tree_offset_m=2.0,
            roadside_tree_intersection_clearance_m=1.0,
            roadside_tree_merge_distance_m=2.0,
            output_root=str(Path(tmp) / "anchor_export_probe"),
        )
        dem_surface = {
            "x": np.array([-10.0, 0.0, 10.0]),
            "y": np.array([-10.0, 0.0, 10.0]),
            "z": np.array([[10.0, 10.0, 10.0], [12.0, 12.0, 12.0], [14.0, 14.0, 14.0]]),
            "metadata": {"status": "success", "source": "unit_test_dem"},
        }
        local = {
            "buildings": gpd.GeoDataFrame(
                [{"osm_id": "unit_building", "source": "unit", "confidence": 1.0, "height_m": 8.0}],
                geometry=[Polygon([(-4, -4), (4, -4), (4, 4), (-4, 4), (-4, -4)])],
                crs=None,
            ),
            "roads": gpd.GeoDataFrame(
                [{"osm_id": "unit_road", "source": "unit", "confidence": 1.0, "width_m": 2.0}],
                geometry=[LineString([(-8, -8), (8, 8)])],
                crs=None,
            ),
            "water": gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=None),
            "green": gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=None),
            "poi": gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=None),
        }
        runs, mapping_df = build_sparse_runs(local, config, dem_surface)
        layers = voxel_layer_names(config)
        building_runs = runs[(runs["layer"] == layers["buildings"]) & (runs["element_id"] == "building_unit_building_0")]
        if building_runs.empty:
            raise AssertionError("Expected anchored building runs to be generated")
        if building_runs["z_min"].nunique() != 1:
            raise AssertionError(f"Building base should be a single anchor elevation, got z_min values {sorted(building_runs['z_min'].unique())}")
        base_runs = runs[(runs["layer"] == layers["building_bases"]) & (runs["element_id"] == "building_base_unit_building_0")]
        if base_runs.empty:
            raise AssertionError("Expected building plinth/base runs on the sloped DEM")
        tree_mapping = mapping_df[mapping_df["element_id"] == "tree_canopy_samples"]
        if tree_mapping.empty or "road centerline-derived street tree" not in str(tree_mapping.iloc[0].get("source", "")):
            raise AssertionError("Expected road-centerline-derived street trees in tree canopy mapping")

        dirs = ensure_dirs(config)
        rhino_meta = export_rhino(runs, mapping_df, config, dirs, local, dem_surface)
        layer_csv = dirs["rhino"] / "final_city_voxel_2m_layers.csv"
        layer_text = layer_csv.read_text(encoding="utf-8-sig")
        for expected in [layers["building_bases"], layers["road_centerlines"], layers["lcz_info"], layers["geo_info"]]:
            if expected not in layer_text:
                raise AssertionError(f"Expected Rhino layer missing: {expected}")
        if rhino_meta.get("road_centerline_curve_count") != 1:
            raise AssertionError(f"Expected one road centerline curve, got {rhino_meta.get('road_centerline_curve_count')}")
        if rhino_meta.get("building_group_count", 0) < 1:
            raise AssertionError(f"Expected at least one Rhino building group, got {rhino_meta.get('building_group_count')}")
        if not rhino_meta.get("building_unit_voxel_expanded"):
            raise AssertionError(f"Expected building unit voxel expansion, got metadata {rhino_meta}")
        if rhino_meta.get("lcz_info_text_count", 0) < 3:
            raise AssertionError(f"Expected LCZ/morphology text dots, got {rhino_meta.get('lcz_info_text_count')}")
        if rhino_meta.get("geo_info_text_count", 0) < 6:
            raise AssertionError(f"Expected geographic coordinate text dots, got {rhino_meta.get('geo_info_text_count')}")
        if rhino_meta.get("geo_info_layer") != layers["geo_info"]:
            raise AssertionError(f"Unexpected geographic coordinate layer metadata: {rhino_meta.get('geo_info_layer')}")
        if rhino_meta.get("clean_mesh_wire_object_count", 0) < 1:
            raise AssertionError(f"Expected clean mesh wire display on Rhino mesh objects, got {rhino_meta.get('clean_mesh_wire_object_count')}")
    return {
        "whole_building_anchor": "passed",
        "building_base_layer": "passed",
        "road_centerline_rhino_layer": "passed",
        "roadside_tree_layout": "passed",
        "rhino_building_groups": "passed",
        "rhino_lcz_info_layer": "passed",
        "rhino_geo_info_layer": "passed",
        "rhino_clean_mesh_wire_display": "passed",
    }


def test_existing_arch_art_output() -> dict:
    output_root = PROJECT_ROOT / "outputs_citylbm_voxel_china" / "dlut_arch_art_college_500m_0p1m"
    if not output_root.exists():
        return {"existing_arch_art_output": "skipped_missing_output"}
    result = qa_site_output(
        output_root,
        expected_lat=DLUT_ARCH_ART_WGS84_LAT,
        expected_lon=DLUT_ARCH_ART_WGS84_LON,
        expected_aoi_width_m=500.0,
        expected_voxel_size_m=0.1,
    )
    if result["status"] != "passed":
        raise AssertionError(f"Existing architecture/art output failed QA: {result['errors']}")
    return {
        "existing_arch_art_output": "passed",
        "rhino_objects": result["rhino_summary"]["object_count"],
        "rhino_layers": result["rhino_summary"]["layer_count"],
        "table_rows": result["table_rows"],
    }


def main() -> None:
    result = {
        "status": "success",
        "coordinate_normalization": test_coordinate_normalization(),
        "minimal_qa_bundle": test_minimal_qa_bundle(),
        "dynamic_rhino_name": test_dynamic_rhino_name_qa_discovery(),
        "strict_real_data_default": test_run_site_model_strict_real_data_default(),
        "building_anchor_and_road_centerline": test_building_anchor_and_road_centerline_export(),
        "existing_output": test_existing_arch_art_output(),
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
