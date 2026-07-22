from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import platform
import re
import shutil
import sys
import time
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import geopandas as gpd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
import numpy as np
import pandas as pd
import requests
import rhino3dm
from PIL import Image
from shapely.geometry import LineString, Point, Polygon, box, mapping, shape
from shapely.ops import unary_union

from data_source_registry import export_registry

try:
    import rasterio
    from rasterio.features import shapes as raster_shapes
    from rasterio.mask import mask as raster_mask
except Exception:
    rasterio = None
    raster_shapes = None
    raster_mask = None


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_ROOT = PROJECT_ROOT / "outputs_citylbm_voxel_china"
PIPELINE_VERSION = "0.2.2"

LAYER_ROLE_COLORS: dict[str, tuple[int, int, int, int]] = {
    "aoi": (255, 220, 80, 255),
    "buildings": (196, 40, 27, 255),
    "building_bases": (118, 67, 46, 255),
    "roads": (55, 55, 55, 255),
    "road_centerlines": (250, 235, 95, 255),
    "water": (65, 155, 223, 255),
    "trees": (57, 125, 33, 255),
    "grass": (136, 176, 83, 255),
    "terrain": (165, 155, 143, 255),
    "poi": (230, 92, 35, 255),
    "lcz_info": (35, 35, 35, 255),
    "geo_info": (28, 93, 153, 255),
}

LAYER_COLORS: dict[str, tuple[int, int, int, int]] = {
    "00_AOI_Boundary": LAYER_ROLE_COLORS["aoi"],
    "01_Buildings_0p1m_Voxels": LAYER_ROLE_COLORS["buildings"],
    "01a_Building_Bases_0p1m_Voxels": LAYER_ROLE_COLORS["building_bases"],
    "02_Roads_Hardscape_0p1m_Voxels": LAYER_ROLE_COLORS["roads"],
    "02a_Road_Centerlines_Vector": LAYER_ROLE_COLORS["road_centerlines"],
    "03_Water_0p1m_Voxels": LAYER_ROLE_COLORS["water"],
    "04_Green_Trees_0p1m_Voxels": LAYER_ROLE_COLORS["trees"],
    "05_Green_Grass_0p1m_Voxels": LAYER_ROLE_COLORS["grass"],
    "06_Terrain_DEM_0p1m_Voxels": LAYER_ROLE_COLORS["terrain"],
    "07_POI_Function_Labels": LAYER_ROLE_COLORS["poi"],
    "08_LCZ_Morphology_Info_Text": LAYER_ROLE_COLORS["lcz_info"],
    "09_Geographic_Coordinate_Info": LAYER_ROLE_COLORS["geo_info"],
}

SCORE_WEIGHTS = {
    "source_selection_score": {
        "coverage_score": 0.35,
        "geometry_quality_score": 0.25,
        "attribute_completeness_score": 0.15,
        "recency_score": 0.10,
        "license_reproducibility_score": 0.10,
        "china_applicability_score": 0.05,
    },
    "height_confidence_score": {
        "height_source_reliability": 0.40,
        "cross_source_consistency": 0.25,
        "local_context_plausibility": 0.20,
        "geometry_validity_score": 0.15,
    },
    "voxelization_readiness_score": {
        "geometry_validity_score": 0.30,
        "height_confidence_score": 0.25,
        "crs_confidence_score": 0.20,
        "source_selection_score": 0.15,
        "topology_cleanliness_score": 0.10,
    },
    "final_model_quality_score": {
        "building_coverage_quality": 0.25,
        "height_attribute_quality": 0.20,
        "road_network_quality": 0.15,
        "terrain_quality": 0.10,
        "green_water_semantic_quality": 0.10,
        "crs_and_alignment_quality": 0.10,
        "voxelization_completeness": 0.10,
    },
}


@dataclass
class RunConfig:
    site_name: str = "dut_west_campus_lingxi_library_500m_0p1m"
    site_name_cn: str = "大连理工大学西部校区令希图书馆500m AOI"
    center_lat: float = 38.8831553
    center_lon: float = 121.5120457
    half_size_m: float = 250.0
    buffer_m: float = 0.0
    voxel_size_m: float = 1.0
    vertical_extent_m: float = 80.0
    allow_resolution_fallback: bool = False
    max_voxel_count_before_tiling: int = 500_000_000
    overpass_timeout_s: int = 45
    random_seed: int = 42
    rhino_version: int = 7
    rhino_export_mode: str = "component_mesh_groups"
    group_buildings_in_rhino: bool = True
    rhino_unit_voxel_max_boxes: int = 1_000_000
    rhino_unit_voxel_mesh_chunk_boxes: int = 20_000
    rhino_component_mesh_max_runs: int = 500_000
    rhino_clean_mesh_wire_display: bool = True
    rhino_geo_info_text_enabled: bool = True
    lcz_info_text_enabled: bool = True
    generate_roadside_trees: bool = True
    roadside_tree_spacing_m: float = 10.0
    roadside_tree_offset_m: float = 2.0
    roadside_tree_intersection_clearance_m: float = 8.0
    roadside_tree_merge_distance_m: float = 4.0
    roadside_tree_max_count: int = 240
    dem_source: str = "aws_terrarium"
    dem_tile_zoom: int = 14
    esa_worldcover_path: str = ""
    esa_worldcover_autodiscover: bool = True
    use_esa_worldcover_landcover: bool = True
    replace_fallback_vegetation_with_worldcover: bool = True
    output_root: str = ""
    strict_real_data: bool = False


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def config_output_root(config: RunConfig | None = None) -> Path:
    if config and config.output_root:
        root = Path(config.output_root).expanduser()
        return root if root.is_absolute() else PROJECT_ROOT / root
    return OUTPUT_ROOT


def rel_project_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def ensure_dirs(config: RunConfig | None = None) -> dict[str, Path]:
    root = config_output_root(config)
    dirs = {
        "root": root,
        "raw": root / "01_raw",
        "gis": root / "02_gis",
        "cache": root / "03_cache",
        "voxels": root / "04_voxels",
        "rhino": root / "05_rhino",
        "tables": root / "06_tables",
        "audit": root / "07_audit",
        "figures": root / "10_figures",
        "docs": root / "11_docs",
        "logs": root / "12_logs",
    }
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def safe_filename(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return slug or "site"


def voxel_size_slug(voxel_size_m: float) -> str:
    text = f"{float(voxel_size_m):g}".replace("-", "m")
    return f"{text.replace('.', 'p')}m"


def rhino_output_base(config: RunConfig) -> str:
    return f"final_city_voxel_{voxel_size_slug(config.voxel_size_m)}"


def voxel_layer_names(config: RunConfig) -> dict[str, str]:
    suffix = voxel_size_slug(config.voxel_size_m)
    return {
        "aoi": "00_AOI_Boundary",
        "buildings": f"01_Buildings_{suffix}_Voxels",
        "building_bases": f"01a_Building_Bases_{suffix}_Voxels",
        "roads": f"02_Roads_Hardscape_{suffix}_Voxels",
        "road_centerlines": "02a_Road_Centerlines_Vector",
        "water": f"03_Water_{suffix}_Voxels",
        "trees": f"04_Green_Trees_{suffix}_Voxels",
        "grass": f"05_Green_Grass_{suffix}_Voxels",
        "terrain": f"06_Terrain_DEM_{suffix}_Voxels",
        "poi": "07_POI_Function_Labels",
        "lcz_info": "08_LCZ_Morphology_Info_Text",
        "geo_info": "09_Geographic_Coordinate_Info",
    }


def layer_color_map(config: RunConfig) -> dict[str, tuple[int, int, int, int]]:
    names = voxel_layer_names(config)
    return {names[role]: rgba for role, rgba in LAYER_ROLE_COLORS.items()}


def local_xy(lon: float, lat: float, center_lon: float, center_lat: float) -> tuple[float, float]:
    earth = 6_378_137.0
    x = math.radians(lon - center_lon) * earth * math.cos(math.radians(center_lat))
    y = math.radians(lat - center_lat) * earth
    return x, y


def lonlat_from_xy(x: float, y: float, center_lon: float, center_lat: float) -> tuple[float, float]:
    earth = 6_378_137.0
    lon = center_lon + math.degrees(x / (earth * math.cos(math.radians(center_lat))))
    lat = center_lat + math.degrees(y / earth)
    return lon, lat


def bbox_lonlat(config: RunConfig) -> dict[str, float]:
    half = config.half_size_m + config.buffer_m
    west, south = lonlat_from_xy(-half, -half, config.center_lon, config.center_lat)
    east, north = lonlat_from_xy(half, half, config.center_lon, config.center_lat)
    return {"west": west, "south": south, "east": east, "north": north, "center": [config.center_lat, config.center_lon]}


def osm_aoi_cache_key(config: RunConfig) -> str:
    bb = bbox_lonlat(config)
    payload = {
        "schema": "osm_overpass_combined_v2",
        "west": round(float(bb["west"]), 6),
        "south": round(float(bb["south"]), 6),
        "east": round(float(bb["east"]), 6),
        "north": round(float(bb["north"]), 6),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def osm_shared_cache_path(config: RunConfig) -> Path:
    return OUTPUT_ROOT / "01_raw" / f"osm_overpass_combined_aoi_{osm_aoi_cache_key(config)}.json"


def lonlat_to_webmercator_tile(lon: float, lat: float, zoom: int) -> tuple[int, int, float, float]:
    lat_rad = math.radians(max(min(lat, 85.05112878), -85.05112878))
    n = 2 ** zoom
    x_float = (lon + 180.0) / 360.0 * n
    y_float = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * n
    tile_x = int(math.floor(x_float))
    tile_y = int(math.floor(y_float))
    pixel_x = (x_float - tile_x) * 256.0
    pixel_y = (y_float - tile_y) * 256.0
    return tile_x, tile_y, pixel_x, pixel_y


def decode_terrarium_png(content: bytes) -> np.ndarray:
    image = Image.open(io.BytesIO(content)).convert("RGB")
    arr = np.asarray(image, dtype=np.float32)
    return arr[:, :, 0] * 256.0 + arr[:, :, 1] + arr[:, :, 2] / 256.0 - 32768.0


def fetch_dem_tile(tile_x: int, tile_y: int, zoom: int, dirs: dict[str, Path]) -> np.ndarray:
    tile_dir = dirs["cache"] / "dem_tiles" / str(zoom)
    tile_dir.mkdir(parents=True, exist_ok=True)
    tile_path = tile_dir / f"{tile_x}_{tile_y}.png"
    shared_tile_path = OUTPUT_ROOT / "03_cache" / "dem_tiles" / str(zoom) / f"{tile_x}_{tile_y}.png"
    if tile_path.exists():
        content = tile_path.read_bytes()
        if shared_tile_path != tile_path and not shared_tile_path.exists():
            shared_tile_path.parent.mkdir(parents=True, exist_ok=True)
            shared_tile_path.write_bytes(content)
        return decode_terrarium_png(content)
    if shared_tile_path.exists() and shared_tile_path != tile_path:
        shutil.copy2(shared_tile_path, tile_path)
        return decode_terrarium_png(tile_path.read_bytes())
    url = f"https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{zoom}/{tile_x}/{tile_y}.png"
    resp = requests.get(url, timeout=30, headers={"User-Agent": "CityLBM-VoxCity DEM sampler"})
    resp.raise_for_status()
    tile_path.write_bytes(resp.content)
    if shared_tile_path != tile_path:
        shared_tile_path.parent.mkdir(parents=True, exist_ok=True)
        shared_tile_path.write_bytes(resp.content)
    return decode_terrarium_png(resp.content)


def sample_dem_tiles(lons: np.ndarray, lats: np.ndarray, config: RunConfig, dirs: dict[str, Path]) -> np.ndarray:
    flat_lons = lons.ravel()
    flat_lats = lats.ravel()
    out = np.empty_like(flat_lons, dtype=np.float32)
    tile_cache: dict[tuple[int, int], np.ndarray] = {}
    for i, (lon, lat) in enumerate(zip(flat_lons, flat_lats)):
        tx, ty, px, py = lonlat_to_webmercator_tile(float(lon), float(lat), config.dem_tile_zoom)
        key = (tx, ty)
        if key not in tile_cache:
            tile_cache[key] = fetch_dem_tile(tx, ty, config.dem_tile_zoom, dirs)
        tile = tile_cache[key]
        ix = int(np.clip(round(px), 0, 255))
        iy = int(np.clip(round(py), 0, 255))
        out[i] = tile[iy, ix]
    return out.reshape(lons.shape)


def fetch_dem_surface(config: RunConfig, dirs: dict[str, Path]) -> dict[str, Any]:
    size = config.half_size_m * 2.0
    sample_count = int(min(161, max(51, round(size / 5.0) + 1)))
    xs = np.linspace(-config.half_size_m, config.half_size_m, sample_count)
    ys = np.linspace(-config.half_size_m, config.half_size_m, sample_count)
    xx, yy = np.meshgrid(xs, ys)
    lonlat = np.vectorize(lambda x, y: lonlat_from_xy(float(x), float(y), config.center_lon, config.center_lat), otypes=[float, float])
    lon_grid, lat_grid = lonlat(xx, yy)
    metadata: dict[str, Any] = {
        "source": config.dem_source,
        "tile_zoom": config.dem_tile_zoom,
        "sample_count_x": sample_count,
        "sample_count_y": sample_count,
        "grid_spacing_m": round(size / (sample_count - 1), 3),
        "timestamp": now_iso(),
    }
    try:
        if config.dem_source != "aws_terrarium":
            raise ValueError(f"unsupported dem_source={config.dem_source}")
        zz = sample_dem_tiles(lon_grid, lat_grid, config, dirs)
        metadata.update({
            "status": "success",
            "license_note": "Mapzen/AWS elevation-tiles-prod Terrarium DEM tiles; derived from open global DEM sources.",
            "min_elevation_m": round(float(np.nanmin(zz)), 3),
            "max_elevation_m": round(float(np.nanmax(zz)), 3),
            "mean_elevation_m": round(float(np.nanmean(zz)), 3),
            "elevation_range_m": round(float(np.nanmax(zz) - np.nanmin(zz)), 3),
        })
    except Exception as exc:
        zz = terrain_z(xx, yy, config, dem_surface=None)
        metadata.update({
            "status": "fallback_procedural",
            "error": str(exc),
            "license_note": "Procedural fallback only; not measured DEM.",
            "min_elevation_m": round(float(np.nanmin(zz)), 3),
            "max_elevation_m": round(float(np.nanmax(zz)), 3),
            "mean_elevation_m": round(float(np.nanmean(zz)), 3),
            "elevation_range_m": round(float(np.nanmax(zz) - np.nanmin(zz)), 3),
        })
    dem_df = pd.DataFrame({
        "x_m": xx.ravel(),
        "y_m": yy.ravel(),
        "lon": lon_grid.ravel(),
        "lat": lat_grid.ravel(),
        "z_m": np.asarray(zz).ravel(),
    })
    dem_df.to_csv(dirs["gis"] / "terrain_dem_samples.csv", index=False, encoding="utf-8-sig")
    write_json(dirs["gis"] / "terrain_dem_metadata.json", metadata)
    return {"x": xs, "y": ys, "z": np.asarray(zz, dtype=float), "metadata": metadata}


ESA_WORLDCOVER_CLASSES = {
    10: {"label": "tree_cover", "semantic": "tree"},
    20: {"label": "shrubland", "semantic": "green"},
    30: {"label": "grassland", "semantic": "green"},
    40: {"label": "cropland", "semantic": "green"},
    50: {"label": "built_up", "semantic": "built"},
    60: {"label": "bare_sparse_vegetation", "semantic": "bare"},
    70: {"label": "snow_and_ice", "semantic": "other"},
    80: {"label": "permanent_water_bodies", "semantic": "water"},
    90: {"label": "herbaceous_wetland", "semantic": "green"},
    95: {"label": "mangroves", "semantic": "tree"},
    100: {"label": "moss_and_lichen", "semantic": "green"},
}


def esa_worldcover_tile_prefix(lat_origin: int, lon_origin: int) -> str:
    lat_prefix = f"N{abs(lat_origin):02d}" if lat_origin >= 0 else f"S{abs(lat_origin):02d}"
    lon_prefix = f"E{abs(lon_origin):03d}" if lon_origin >= 0 else f"W{abs(lon_origin):03d}"
    return f"{lat_prefix}{lon_prefix}"


def expected_esa_worldcover_tiles(config: RunConfig) -> list[str]:
    bb = bbox_lonlat(config)
    tile_size_deg = 3
    lon_start = int(math.floor(bb["west"] / tile_size_deg) * tile_size_deg)
    lon_end = int(math.floor((bb["east"] - 1e-12) / tile_size_deg) * tile_size_deg)
    lat_start = int(math.floor(bb["south"] / tile_size_deg) * tile_size_deg)
    lat_end = int(math.floor((bb["north"] - 1e-12) / tile_size_deg) * tile_size_deg)
    names: list[str] = []
    for lat_origin in range(lat_start, lat_end + tile_size_deg, tile_size_deg):
        for lon_origin in range(lon_start, lon_end + tile_size_deg, tile_size_deg):
            names.append(f"ESA_WorldCover_10m_2021_v200_{esa_worldcover_tile_prefix(lat_origin, lon_origin)}_Map.tif")
    return names


def discover_esa_worldcover_candidates(config: RunConfig, dirs: dict[str, Path]) -> list[Path]:
    if config.esa_worldcover_path:
        path = Path(config.esa_worldcover_path).expanduser()
        return [path] if path.exists() else []
    if not config.esa_worldcover_autodiscover:
        return []
    search_dirs = [
        PROJECT_ROOT / "data" / "gee",
        PROJECT_ROOT / "data",
        dirs["raw"],
        OUTPUT_ROOT / "01_raw",
        Path.home() / "Downloads",
    ]
    patterns = ["*WorldCover*.tif", "*WorldCover*.tiff", "*ESA*.tif", "*ESA*.tiff", "*landcover*.tif", "*land_cover*.tif"]
    candidates: list[Path] = []
    for directory in search_dirs:
        if not directory.exists():
            continue
        for pattern in patterns:
            candidates.extend(path for path in directory.rglob(pattern) if path.is_file())
    deduped = sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)
    return deduped


def worldcover_manifest_paths(config: RunConfig, dirs: dict[str, Path]) -> list[Path]:
    paths = [
        dirs["logs"] / "worldcover_tile_request_manifest.json",
        config_output_root(config) / "12_logs" / "worldcover_tile_request_manifest.json",
        OUTPUT_ROOT / "12_logs" / "worldcover_tile_request_manifest.json",
    ]
    deduped: list[Path] = []
    for path in paths:
        if path not in deduped:
            deduped.append(path)
    return deduped


def worldcover_expected_bytes_by_name(config: RunConfig, dirs: dict[str, Path]) -> dict[str, int]:
    expected: dict[str, int] = {}
    for manifest_path in worldcover_manifest_paths(config, dirs):
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        for site in manifest.get("sites", []):
            for tile in site.get("tiles", []):
                name = tile.get("tile_name")
                bytes_value = tile.get("expected_download_bytes")
                if not name or bytes_value in (None, ""):
                    continue
                try:
                    expected.setdefault(str(name), int(bytes_value))
                except (TypeError, ValueError):
                    continue
    return expected


def worldcover_size_check(path: Path, expected_bytes_by_name: dict[str, int]) -> dict[str, Any]:
    result: dict[str, Any] = {"path": str(path), "name": path.name, "status": "unchecked"}
    expected = expected_bytes_by_name.get(path.name)
    if expected is None:
        return result
    result["expected_download_bytes"] = expected
    try:
        local_bytes = path.stat().st_size
    except OSError as exc:
        result.update({"status": "stat_error", "error": str(exc)})
        return result
    result["bytes"] = local_bytes
    result["status"] = "complete" if local_bytes == expected else "file_size_mismatch"
    return result


def select_esa_worldcover_raster(config: RunConfig, dirs: dict[str, Path]) -> dict[str, Any]:
    candidates = discover_esa_worldcover_candidates(config, dirs)
    expected_bytes = worldcover_expected_bytes_by_name(config, dirs)
    bb = bbox_lonlat(config)
    aoi_wgs84 = box(bb["west"], bb["south"], bb["east"], bb["north"])
    details: list[dict[str, Any]] = []
    if rasterio is None:
        valid_candidates = []
        for path in candidates:
            size_check = worldcover_size_check(path, expected_bytes)
            if size_check.get("status") != "file_size_mismatch":
                valid_candidates.append(path)
        return {
            "selected_path": str(valid_candidates[0]) if valid_candidates else None,
            "selection_status": "unchecked_missing_rasterio" if valid_candidates else "missing_coverage" if candidates else "missing_raster",
            "candidate_count": len(candidates),
            "candidates": [{"path": str(path), "size_check": worldcover_size_check(path, expected_bytes)} for path in candidates[:20]],
            "aoi_bbox_wgs84": bb,
            "expected_tiles": expected_esa_worldcover_tiles(config),
        }
    selected: Path | None = None
    for candidate in candidates:
        info: dict[str, Any] = {"path": str(candidate), "intersects_aoi": False}
        size_check = worldcover_size_check(candidate, expected_bytes)
        info["size_check"] = size_check
        if size_check.get("status") == "file_size_mismatch":
            info["error"] = "file_size_mismatch"
            details.append(info)
            continue
        try:
            with rasterio.open(candidate) as src:
                info.update({
                    "crs": str(src.crs) if src.crs else None,
                    "bounds": [float(v) for v in src.bounds],
                })
                if src.crs is None:
                    info["error"] = "missing_crs"
                    details.append(info)
                    continue
                aoi_src = gpd.GeoDataFrame([{"geometry": aoi_wgs84}], crs="EPSG:4326").to_crs(src.crs).geometry.iloc[0]
                intersects = bool(box(*src.bounds).intersects(aoi_src))
                info["intersects_aoi"] = intersects
                if intersects and selected is None:
                    selected = candidate
        except Exception as exc:
            info["error"] = str(exc)
        details.append(info)
    return {
        "selected_path": str(selected) if selected else None,
        "selection_status": "selected_intersecting_raster" if selected else "missing_coverage" if candidates else "missing_raster",
        "candidate_count": len(candidates),
        "invalid_candidate_count": sum(1 for item in details if item.get("error") == "file_size_mismatch"),
        "candidates": details[:20],
        "aoi_bbox_wgs84": bb,
        "expected_tiles": expected_esa_worldcover_tiles(config),
    }


def find_esa_worldcover_path(config: RunConfig, dirs: dict[str, Path]) -> Path | None:
    selection = select_esa_worldcover_raster(config, dirs)
    selected = selection.get("selected_path")
    return Path(selected) if selected else None


def empty_landcover_result(metadata: dict[str, Any]) -> dict[str, Any]:
    empty = gpd.GeoDataFrame(columns=["source", "class_value", "class_label", "kind", "confidence", "geometry"], geometry="geometry", crs="EPSG:4326")
    return {"green": empty.copy(), "water": empty.copy(), "metadata": metadata}


def load_esa_worldcover_landcover(config: RunConfig, dirs: dict[str, Path]) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "ESA WorldCover 2021 local GeoTIFF",
        "status": "disabled",
        "timestamp": now_iso(),
        "path": None,
        "green_feature_count": 0,
        "water_feature_count": 0,
        "tree_feature_count": 0,
    }
    if not config.use_esa_worldcover_landcover:
        write_json(dirs["tables"] / "esa_worldcover_landcover_metadata.json", metadata)
        return empty_landcover_result(metadata)
    if rasterio is None or raster_mask is None or raster_shapes is None:
        metadata.update({"status": "missing_dependency", "error": "rasterio is required to read GeoTIFF WorldCover exports"})
        write_json(dirs["tables"] / "esa_worldcover_landcover_metadata.json", metadata)
        return empty_landcover_result(metadata)
    raster_selection = select_esa_worldcover_raster(config, dirs)
    metadata["raster_selection"] = raster_selection
    selected_path = raster_selection.get("selected_path")
    raster_path = Path(selected_path) if selected_path else None
    if raster_path is None:
        metadata.update({
            "status": raster_selection.get("selection_status", "missing_raster"),
            "expected": "Set RunConfig.esa_worldcover_path or place matching WorldCover GeoTIFF tiles in data/gee, data, 01_raw, or Downloads.",
            "expected_tiles": raster_selection.get("expected_tiles", []),
        })
        write_json(dirs["tables"] / "esa_worldcover_landcover_metadata.json", metadata)
        return empty_landcover_result(metadata)

    bb = bbox_lonlat(config)
    aoi_wgs84 = box(bb["west"], bb["south"], bb["east"], bb["north"])
    try:
        with rasterio.open(raster_path) as src:
            if src.crs is None:
                raise ValueError("WorldCover raster has no CRS")
            raster_crs = str(src.crs)
            aoi_src = gpd.GeoDataFrame([{"geometry": aoi_wgs84}], crs="EPSG:4326").to_crs(src.crs).geometry.iloc[0]
            arr, transform = raster_mask(src, [mapping(aoi_src)], crop=True, filled=True)
            band = arr[0]
            nodata = src.nodata
            valid_mask = np.ones(band.shape, dtype=bool)
            if nodata is not None:
                valid_mask &= band != nodata
            valid_mask &= np.isfinite(band)
            rows = {"green": [], "water": []}
            class_counts: dict[str, int] = {}
            for geom_mapping, value in raster_shapes(band.astype(np.int16), mask=valid_mask, transform=transform):
                class_value = int(value)
                info = ESA_WORLDCOVER_CLASSES.get(class_value)
                if info is None:
                    continue
                semantic = info["semantic"]
                if semantic not in {"green", "tree", "water"}:
                    continue
                geom_src = shape(geom_mapping)
                if geom_src.is_empty:
                    continue
                geom_wgs84 = gpd.GeoSeries([geom_src], crs=src.crs).to_crs("EPSG:4326").iloc[0].intersection(aoi_wgs84)
                if geom_wgs84.is_empty:
                    continue
                target = "water" if semantic == "water" else "green"
                kind = info["label"]
                rows[target].append({
                    "source": "ESA WorldCover 2021 local GeoTIFF",
                    "license": "ESA WorldCover open data; verify export-year terms for publication",
                    "source_crs": str(src.crs),
                    "class_value": class_value,
                    "class_label": info["label"],
                    "kind": kind,
                    "confidence": 0.82 if target == "green" else 0.85,
                    "geometry": geom_wgs84,
                })
                class_counts[str(class_value)] = class_counts.get(str(class_value), 0) + 1
        green = gpd.GeoDataFrame(rows["green"], geometry="geometry", crs="EPSG:4326") if rows["green"] else empty_landcover_result({})["green"]
        water = gpd.GeoDataFrame(rows["water"], geometry="geometry", crs="EPSG:4326") if rows["water"] else empty_landcover_result({})["water"]
        metadata.update({
            "status": "success",
            "path": str(raster_path),
            "green_feature_count": int(len(green)),
            "water_feature_count": int(len(water)),
            "tree_feature_count": int((green.get("kind", pd.Series(dtype=str)) == "tree_cover").sum()) if not green.empty else 0,
            "class_polygon_counts": class_counts,
            "raster_crs": raster_crs,
            "selected_path": str(raster_path),
        })
        if not green.empty:
            green.to_file(dirs["gis"] / "worldcover_green.gpkg", driver="GPKG", engine="pyogrio")
        if not water.empty:
            water.to_file(dirs["gis"] / "worldcover_water.gpkg", driver="GPKG", engine="pyogrio")
        write_json(dirs["tables"] / "esa_worldcover_landcover_metadata.json", metadata)
        return {"green": green, "water": water, "metadata": metadata}
    except Exception as exc:
        metadata.update({"status": "failed", "path": str(raster_path), "error": str(exc)})
        write_json(dirs["tables"] / "esa_worldcover_landcover_metadata.json", metadata)
        return empty_landcover_result(metadata)


def fuse_worldcover_landcover(layers: dict[str, gpd.GeoDataFrame], landcover: dict[str, Any], dirs: dict[str, Path]) -> dict[str, gpd.GeoDataFrame]:
    metadata = landcover.get("metadata", {})
    fused = dict(layers)
    osm_tree_like = gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs=layers["green"].crs)
    if not layers["green"].empty:
        kind = layers["green"].get("kind", pd.Series("", index=layers["green"].index)).astype(str)
        geom_type = layers["green"].geometry.geom_type.astype(str)
        tree_mask = kind.isin(["tree", "tree_row"]) | geom_type.isin(["Point", "LineString", "MultiLineString"])
        osm_tree_like = layers["green"][tree_mask].copy()
    if metadata.get("status") == "success":
        green = landcover.get("green")
        water = landcover.get("water")
        if isinstance(green, gpd.GeoDataFrame) and not green.empty:
            if not osm_tree_like.empty:
                fused["green"] = gpd.GeoDataFrame(pd.concat([green, osm_tree_like], ignore_index=True), geometry="geometry", crs=green.crs)
            else:
                fused["green"] = green
        if isinstance(water, gpd.GeoDataFrame):
            fused["water"] = water
    write_json(dirs["tables"] / "landcover_fusion_decision.json", {
        "timestamp": now_iso(),
        "worldcover_status": metadata.get("status"),
        "green_source": "ESA WorldCover 2021 local GeoTIFF" if metadata.get("status") == "success" and not fused["green"].empty and "ESA WorldCover" in str(fused["green"].get("source", "").iloc[0]) else "OpenStreetMap/procedural fallback path",
        "water_source": "ESA WorldCover 2021 local GeoTIFF" if metadata.get("status") == "success" and not fused["water"].empty and "ESA WorldCover" in str(fused["water"].get("source", "").iloc[0]) else "OpenStreetMap/procedural fallback path",
        "replace_fallback_vegetation": metadata.get("status") == "success",
        "retained_osm_tree_like_feature_count": int(len(osm_tree_like)),
    })
    return fused


def sample_dem_surface(x: np.ndarray | float, y: np.ndarray | float, dem_surface: dict[str, Any]) -> np.ndarray:
    xs = np.asarray(dem_surface["x"], dtype=float)
    ys = np.asarray(dem_surface["y"], dtype=float)
    grid = np.asarray(dem_surface["z"], dtype=float)
    x_arr = np.asarray(x, dtype=float)
    y_arr = np.asarray(y, dtype=float)
    x_clip = np.clip(x_arr, xs[0], xs[-1])
    y_clip = np.clip(y_arr, ys[0], ys[-1])
    ix = np.clip(np.searchsorted(xs, x_clip, side="right") - 1, 0, len(xs) - 2)
    iy = np.clip(np.searchsorted(ys, y_clip, side="right") - 1, 0, len(ys) - 2)
    x0, x1 = xs[ix], xs[ix + 1]
    y0, y1 = ys[iy], ys[iy + 1]
    tx = np.divide(x_clip - x0, x1 - x0, out=np.zeros_like(x_clip, dtype=float), where=(x1 != x0))
    ty = np.divide(y_clip - y0, y1 - y0, out=np.zeros_like(y_clip, dtype=float), where=(y1 != y0))
    z00 = grid[iy, ix]
    z10 = grid[iy, ix + 1]
    z01 = grid[iy + 1, ix]
    z11 = grid[iy + 1, ix + 1]
    return (1 - tx) * (1 - ty) * z00 + tx * (1 - ty) * z10 + (1 - tx) * ty * z01 + tx * ty * z11


def overpass_query(query: str, cache_path: Path, timeout_s: int) -> tuple[dict, str, str | None]:
    if cache_path.exists():
        return json.loads(cache_path.read_text(encoding="utf-8")), "cache", None
    mirrors = [
        "https://overpass-api.de/api/interpreter",
        "https://overpass.kumi.systems/api/interpreter",
        "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    ]
    last_error = None
    for url in mirrors:
        try:
            resp = requests.post(
                url,
                data={"data": query},
                timeout=timeout_s,
                headers={"User-Agent": "CityLBM-VoxCity-China/1.0 reproducible-research"},
            )
            resp.raise_for_status()
            data = resp.json()
            cache_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            return data, url, None
        except Exception as exc:
            last_error = f"{url}: {exc}"
    fallback = {"elements": [], "fallback_reason": last_error}
    cache_path.write_text(json.dumps(fallback, ensure_ascii=False), encoding="utf-8")
    return fallback, "fallback_empty", last_error


def estimate_building_height(tags: dict[str, Any]) -> tuple[float, int | None, str, float]:
    if tags.get("height"):
        raw = str(tags["height"]).replace("m", "").strip()
        try:
            height = max(2.5, float(raw))
            floors = max(1, round(height / 3.3))
            return height, floors, "OSM height", 0.90
        except ValueError:
            pass
    for key in ("building:levels", "levels"):
        if tags.get(key):
            try:
                floors = max(1, int(float(str(tags[key]))))
                return floors * 3.3, floors, f"OSM {key} * 3.3m", 0.72
            except ValueError:
                pass
    btype = str(tags.get("building", "yes"))
    defaults = {
        "commercial": (16.5, 5),
        "retail": (13.2, 4),
        "apartments": (19.8, 6),
        "residential": (16.5, 5),
        "school": (13.2, 4),
        "university": (16.5, 5),
        "yes": (12.0, 4),
    }
    height, floors = defaults.get(btype, (12.0, 4))
    return height, floors, f"estimated from building type={btype}", 0.45


def geom_from_way(el: dict, nodes: dict[int, tuple[float, float]], closed: bool) -> list[tuple[float, float]]:
    coords = [nodes[nid] for nid in el.get("nodes", []) if nid in nodes]
    if closed and coords and coords[0] != coords[-1]:
        coords.append(coords[0])
    return coords


def fetch_osm_layers(config: RunConfig, dirs: dict[str, Path]) -> tuple[dict[str, gpd.GeoDataFrame], list[dict]]:
    bb = bbox_lonlat(config)
    q = f"""[out:json][timeout:{config.overpass_timeout_s}];
(
  way({bb['south']},{bb['west']},{bb['north']},{bb['east']})["building"];
  way({bb['south']},{bb['west']},{bb['north']},{bb['east']})["highway"];
  way({bb['south']},{bb['west']},{bb['north']},{bb['east']})["natural"="water"];
  way({bb['south']},{bb['west']},{bb['north']},{bb['east']})["waterway"];
  way({bb['south']},{bb['west']},{bb['north']},{bb['east']})["leisure"~"park|garden"];
  way({bb['south']},{bb['west']},{bb['north']},{bb['east']})["landuse"~"grass|forest|recreation_ground|cemetery"];
  way({bb['south']},{bb['west']},{bb['north']},{bb['east']})["natural"~"wood|tree_row|scrub|grassland"];
  node({bb['south']},{bb['west']},{bb['north']},{bb['east']})["natural"="tree"];
  node({bb['south']},{bb['west']},{bb['north']},{bb['east']})["amenity"];
  node({bb['south']},{bb['west']},{bb['north']},{bb['east']})["shop"];
  node({bb['south']},{bb['west']},{bb['north']},{bb['east']})["tourism"];
  node({bb['south']},{bb['west']},{bb['north']},{bb['east']})["public_transport"];
);
out body; >; out skel qt;"""
    raw_cache = dirs["raw"] / f"osm_overpass_combined_raw_v2_{safe_filename(config.site_name)}.json"
    shared_cache = osm_shared_cache_path(config)
    if not raw_cache.exists() and shared_cache.exists():
        shutil.copy2(shared_cache, raw_cache)
    raw, provider, error = overpass_query(q, raw_cache, config.overpass_timeout_s)
    if provider != "fallback_empty" and raw_cache.exists() and not shared_cache.exists():
        shared_cache.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(raw_cache, shared_cache)
    nodes = {el["id"]: (float(el["lon"]), float(el["lat"])) for el in raw.get("elements", []) if el.get("type") == "node" and "lon" in el}
    aoi_poly = Polygon([
        lonlat_from_xy(-config.half_size_m, -config.half_size_m, config.center_lon, config.center_lat),
        lonlat_from_xy(-config.half_size_m, config.half_size_m, config.center_lon, config.center_lat),
        lonlat_from_xy(config.half_size_m, config.half_size_m, config.center_lon, config.center_lat),
        lonlat_from_xy(config.half_size_m, -config.half_size_m, config.center_lon, config.center_lat),
    ])
    rows = {"buildings": [], "roads": [], "water": [], "green": [], "poi": []}
    for el in raw.get("elements", []):
        tags = el.get("tags", {})
        if el.get("type") == "way":
            if "building" in tags:
                coords = geom_from_way(el, nodes, closed=True)
                if len(coords) >= 4:
                    geom = Polygon(coords)
                    if geom.is_valid and geom.intersects(aoi_poly):
                        height, floors, hsrc, hconf = estimate_building_height(tags)
                        rows["buildings"].append({
                            "osm_id": el.get("id"), "name": tags.get("name"), "building": tags.get("building", "yes"),
                            "height_m": height, "floors": floors, "height_source": hsrc, "height_confidence": hconf,
                            "source": "OpenStreetMap Overpass", "license": "ODbL-1.0", "source_crs": "EPSG:4326",
                            "confidence": hconf, "geometry": geom,
                        })
            elif "highway" in tags:
                coords = geom_from_way(el, nodes, closed=False)
                if len(coords) >= 2:
                    geom = LineString(coords)
                    if geom.intersects(aoi_poly):
                        highway = tags.get("highway", "")
                        width = road_width_m(tags)
                        rows["roads"].append({
                            "osm_id": el.get("id"), "name": tags.get("name"), "highway": highway, "width_m": width,
                            "source": "OpenStreetMap Overpass", "license": "ODbL-1.0", "source_crs": "EPSG:4326",
                            "confidence": 0.78, "geometry": geom,
                        })
            elif tags.get("natural") == "water" or "waterway" in tags:
                coords = geom_from_way(el, nodes, closed=True)
                if len(coords) >= 4:
                    geom = Polygon(coords)
                    if geom.is_valid and geom.intersects(aoi_poly):
                        rows["water"].append({
                            "osm_id": el.get("id"), "name": tags.get("name"), "kind": tags.get("waterway") or tags.get("natural"),
                            "source": "OpenStreetMap Overpass", "license": "ODbL-1.0", "source_crs": "EPSG:4326",
                            "confidence": 0.75, "geometry": geom,
                        })
            elif tags.get("natural") == "tree_row":
                coords = geom_from_way(el, nodes, closed=False)
                if len(coords) >= 2:
                    geom = LineString(coords)
                    if geom.intersects(aoi_poly):
                        rows["green"].append({
                            "osm_id": el.get("id"), "name": tags.get("name"), "kind": "tree_row",
                            "source": "OpenStreetMap Overpass", "license": "ODbL-1.0", "source_crs": "EPSG:4326",
                            "confidence": 0.74, "geometry": geom,
                        })
            elif any(k in tags for k in ("leisure", "landuse", "natural")):
                coords = geom_from_way(el, nodes, closed=True)
                if len(coords) >= 4:
                    geom = Polygon(coords)
                    if geom.is_valid and geom.intersects(aoi_poly):
                        rows["green"].append({
                            "osm_id": el.get("id"), "name": tags.get("name"),
                            "kind": tags.get("leisure") or tags.get("landuse") or tags.get("natural"),
                            "source": "OpenStreetMap Overpass", "license": "ODbL-1.0", "source_crs": "EPSG:4326",
                            "confidence": 0.68, "geometry": geom,
                        })
        elif el.get("type") == "node" and tags.get("natural") == "tree":
            geom = Point(float(el["lon"]), float(el["lat"]))
            if geom.intersects(aoi_poly):
                rows["green"].append({
                    "osm_id": el.get("id"), "name": tags.get("name"), "kind": "tree",
                    "source": "OpenStreetMap Overpass", "license": "ODbL-1.0", "source_crs": "EPSG:4326",
                    "confidence": 0.78, "geometry": geom,
                })
        elif el.get("type") == "node" and any(k in tags for k in ("amenity", "shop", "tourism", "public_transport")):
            geom = Point(float(el["lon"]), float(el["lat"]))
            if geom.intersects(aoi_poly):
                rows["poi"].append({
                    "osm_id": el.get("id"), "name": tags.get("name"),
                    "function": tags.get("amenity") or tags.get("shop") or tags.get("tourism") or tags.get("public_transport"),
                    "source": "OpenStreetMap Overpass", "license": "ODbL-1.0", "source_crs": "EPSG:4326",
                    "confidence": 0.70, "geometry": geom,
                })
    def make_gdf(data: list[dict]) -> gpd.GeoDataFrame:
        if data:
            return gpd.GeoDataFrame(data, geometry="geometry", crs="EPSG:4326")
        return gpd.GeoDataFrame({"geometry": []}, geometry="geometry", crs="EPSG:4326")

    layers = {name: make_gdf(data) for name, data in rows.items()}
    audit = [{
        "stage": "fetch_osm",
        "provider": provider,
        "error": error,
        "building_count": len(layers["buildings"]),
        "road_count": len(layers["roads"]),
        "water_count": len(layers["water"]),
        "green_count": len(layers["green"]),
        "poi_count": len(layers["poi"]),
        "raw_cache": str(raw_cache),
        "shared_cache": str(shared_cache),
        "timestamp": now_iso(),
    }]
    if not any(len(gdf) for gdf in layers.values()):
        audit.append({"stage": "fallback", "reason": "OSM unavailable or empty", "timestamp": now_iso()})
    return layers, audit


def road_width_m(tags: dict[str, Any]) -> float:
    if tags.get("width"):
        try:
            return float(str(tags["width"]).replace("m", ""))
        except ValueError:
            pass
    highway = tags.get("highway", "")
    return {
        "motorway": 18.0, "trunk": 16.0, "primary": 14.0, "secondary": 12.0,
        "tertiary": 10.0, "residential": 7.0, "service": 4.5, "footway": 2.0,
        "pedestrian": 6.0, "path": 1.5,
    }.get(highway, 6.0)


def to_local_gdf(gdf: gpd.GeoDataFrame, config: RunConfig) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gpd.GeoDataFrame(gdf.copy(), geometry=[], crs=None)
    def conv_geom(geom):
        if geom.geom_type == "Point":
            x, y = local_xy(geom.x, geom.y, config.center_lon, config.center_lat)
            return Point(x, y)
        if geom.geom_type == "LineString":
            return LineString([local_xy(lon, lat, config.center_lon, config.center_lat) for lon, lat in geom.coords])
        if geom.geom_type == "Polygon":
            return Polygon([local_xy(lon, lat, config.center_lon, config.center_lat) for lon, lat in geom.exterior.coords])
        return geom
    out = gdf.copy()
    out["geometry"] = out.geometry.apply(conv_geom)
    out.crs = None
    aoi = box(-config.half_size_m, -config.half_size_m, config.half_size_m, config.half_size_m)
    out["geometry"] = out.geometry.apply(lambda g: g.intersection(aoi) if not g.is_empty else g)
    out = out[~out.geometry.is_empty].copy()
    return out


def source_score(values: dict[str, float]) -> float:
    return round(sum(values[k] * w for k, w in SCORE_WEIGHTS["source_selection_score"].items()), 4)


def weighted_score(weights_key: str, values: dict[str, float]) -> float:
    return round(sum(values[k] * w for k, w in SCORE_WEIGHTS[weights_key].items()), 4)


def grid_config(config: RunConfig) -> dict[str, Any]:
    size = config.half_size_m * 2.0
    nx = int(round(size / config.voxel_size_m))
    ny = int(round(size / config.voxel_size_m))
    nz = int(round(config.vertical_extent_m / config.voxel_size_m))
    total = nx * ny * nz
    memory_gb = total * 2 / (1024 ** 3)
    file_gb = total * 0.08 / (1024 ** 3)
    category = "small" if total < 50_000_000 else "large" if total < config.max_voxel_count_before_tiling else "tiled_required"
    return {
        "voxel_size_m": config.voxel_size_m,
        "aoi_width_m": size,
        "aoi_height_m": size,
        "vertical_extent_m": config.vertical_extent_m,
        "nx": nx,
        "ny": ny,
        "nz": nz,
        "total_voxel_count_dense_equivalent": total,
        "estimated_memory_gb_uint16_dense": round(memory_gb, 3),
        "estimated_file_size_gb_sparse_expected": round(file_gb, 3),
        "estimated_runtime_category": category,
        "representation": "sparse voxel table; Rhino export may group runs or expand building voxels depending on rhino_export_mode",
        "tiled_output": total > config.max_voxel_count_before_tiling,
        "allow_resolution_fallback": config.allow_resolution_fallback,
        "rhino_export_mode": config.rhino_export_mode,
        "group_buildings_in_rhino": config.group_buildings_in_rhino,
        "rhino_unit_voxel_max_boxes": config.rhino_unit_voxel_max_boxes,
        "rhino_unit_voxel_mesh_chunk_boxes": config.rhino_unit_voxel_mesh_chunk_boxes,
        "rhino_component_mesh_max_runs": config.rhino_component_mesh_max_runs,
        "rhino_clean_mesh_wire_display": config.rhino_clean_mesh_wire_display,
        "rhino_geo_info_text_enabled": config.rhino_geo_info_text_enabled,
        "rhino_unit": "meter",
    }


def terrain_z(x: np.ndarray | float, y: np.ndarray | float, config: RunConfig, dem_surface: dict[str, Any] | None = None) -> np.ndarray | float:
    if dem_surface is not None and dem_surface.get("metadata", {}).get("status") == "success":
        return sample_dem_surface(x, y, dem_surface)
    return 18.0 + 2.0 * np.sin(np.asarray(x) / 42.0) + 1.2 * np.cos(np.asarray(y) / 55.0) + 0.015 * np.asarray(y)


def is_real_dem(dem_surface: dict[str, Any] | None) -> bool:
    return bool(dem_surface and dem_surface.get("metadata", {}).get("status") == "success")


def terrain_element_id(config: RunConfig, dem_surface: dict[str, Any] | None) -> str:
    if is_real_dem(dem_surface):
        return f"terrain_dem_{safe_filename(str((dem_surface or {}).get('metadata', {}).get('source', config.dem_source)))}"
    return "terrain_fallback_procedural"


def polygon_mask(poly: Polygon, config: RunConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    vs = config.voxel_size_m
    minx, miny, maxx, maxy = poly.bounds
    minx = max(-config.half_size_m, math.floor(minx / vs) * vs)
    maxx = min(config.half_size_m, math.ceil(maxx / vs) * vs)
    miny = max(-config.half_size_m, math.floor(miny / vs) * vs)
    maxy = min(config.half_size_m, math.ceil(maxy / vs) * vs)
    xs = np.arange(minx + vs / 2, maxx, vs)
    ys = np.arange(miny + vs / 2, maxy, vs)
    if len(xs) == 0 or len(ys) == 0:
        return xs, ys, np.zeros((0, 0), dtype=bool)
    xx, yy = np.meshgrid(xs, ys)
    path = MplPath(np.asarray(poly.exterior.coords))
    mask = path.contains_points(np.column_stack([xx.ravel(), yy.ravel()])).reshape(len(ys), len(xs))
    return xs, ys, mask


def building_anchor_point(poly: Polygon) -> Point:
    center = poly.centroid
    if not poly.covers(center):
        center = poly.representative_point()
    return center


def terrain_stats_for_mask(mask: np.ndarray, xs: np.ndarray, ys: np.ndarray, config: RunConfig,
                           dem_surface: dict[str, Any] | None = None) -> dict[str, float]:
    if mask.size == 0 or not mask.any():
        return {"min": 0.0, "mean": 0.0, "max": 0.0}
    xx, yy = np.meshgrid(xs, ys)
    values = np.asarray(terrain_z(xx[mask], yy[mask], config, dem_surface), dtype=float)
    return {
        "min": float(np.nanmin(values)),
        "mean": float(np.nanmean(values)),
        "max": float(np.nanmax(values)),
    }


def polygon_parts(geom: Any) -> list[Polygon]:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Polygon":
        return [geom]
    if geom.geom_type == "MultiPolygon":
        return [part for part in geom.geoms if not part.is_empty]
    if geom.geom_type == "GeometryCollection":
        parts: list[Polygon] = []
        for sub in geom.geoms:
            parts.extend(polygon_parts(sub))
        return parts
    return []


def line_parts(geom: Any) -> list[LineString]:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "LineString":
        return [geom]
    if geom.geom_type == "MultiLineString":
        return [part for part in geom.geoms if not part.is_empty]
    if geom.geom_type == "GeometryCollection":
        parts: list[LineString] = []
        for sub in geom.geoms:
            parts.extend(line_parts(sub))
        return parts
    return []


def point_parts(geom: Any) -> list[Point]:
    if geom is None or geom.is_empty:
        return []
    if geom.geom_type == "Point":
        return [geom]
    if geom.geom_type == "MultiPoint":
        return [part for part in geom.geoms if not part.is_empty]
    if geom.geom_type == "LineString":
        coords = list(geom.coords)
        if not coords:
            return []
        return [Point(coords[0]), Point(coords[-1])]
    if geom.geom_type == "MultiLineString":
        points: list[Point] = []
        for part in geom.geoms:
            points.extend(point_parts(part))
        return points
    if geom.geom_type == "GeometryCollection":
        points: list[Point] = []
        for sub in geom.geoms:
            points.extend(point_parts(sub))
        return points
    return []


def sample_points_in_polygon(poly: Polygon, spacing_m: float, max_points: int) -> list[Point]:
    if poly.is_empty or max_points <= 0:
        return []
    minx, miny, maxx, maxy = poly.bounds
    xs = np.arange(minx + spacing_m / 2.0, maxx, spacing_m)
    ys = np.arange(miny + spacing_m / 2.0, maxy, spacing_m)
    points: list[Point] = []
    for y in ys:
        for x in xs:
            point = Point(float(x), float(y))
            if poly.covers(point):
                points.append(point)
                if len(points) >= max_points:
                    return points
    if not points:
        points.append(building_anchor_point(poly))
    return points


def road_junction_points(road_lines: list[LineString]) -> list[Point]:
    junctions: list[Point] = []
    for line in road_lines:
        junctions.extend(point_parts(line))
    for i, first in enumerate(road_lines):
        for second in road_lines[i + 1:]:
            if not first.bounds or not second.bounds:
                continue
            inter = first.intersection(second)
            junctions.extend(point_parts(inter))
    return dedupe_points(junctions, merge_distance_m=2.0)


def dedupe_points(points: list[Point], merge_distance_m: float) -> list[Point]:
    accepted: list[Point] = []
    threshold = max(0.0, float(merge_distance_m))
    for point in points:
        if threshold and any(point.distance(existing) < threshold for existing in accepted):
            continue
        accepted.append(point)
    return accepted


def offset_line_parts(line: LineString, distance_m: float, side: str) -> list[LineString]:
    try:
        shifted = line.parallel_offset(float(distance_m), side, join_style=2)
    except Exception:
        return []
    return line_parts(shifted)


def dedupe_tree_candidates(candidates: list[dict[str, Any]], merge_distance_m: float) -> list[dict[str, Any]]:
    accepted: list[dict[str, Any]] = []
    accepted_points: list[Point] = []
    threshold = max(0.0, float(merge_distance_m))
    for candidate in candidates:
        point = Point(float(candidate["x"]), float(candidate["y"]))
        if threshold and any(point.distance(existing) < threshold for existing in accepted_points):
            continue
        accepted_points.append(point)
        accepted.append(candidate)
    return accepted


def sample_roadside_tree_candidates(roads: gpd.GeoDataFrame, aoi: Polygon, config: RunConfig) -> list[dict[str, Any]]:
    if roads.empty or not config.generate_roadside_trees:
        return []
    spacing = max(float(config.roadside_tree_spacing_m), config.voxel_size_m * 2.0, 1.0)
    offset_from_edge = max(float(config.roadside_tree_offset_m), 0.0)
    clearance = max(float(config.roadside_tree_intersection_clearance_m), 0.0)
    max_count = max(int(config.roadside_tree_max_count), 0)
    if max_count == 0:
        return []

    road_rows: list[tuple[Any, LineString]] = []
    for _, row in roads.iterrows():
        geom = row.geometry.intersection(aoi)
        for line in line_parts(geom):
            if line.length >= spacing * 0.6:
                road_rows.append((row, line))
    if not road_rows:
        return []

    junctions = road_junction_points([line for _, line in road_rows])
    candidates: list[dict[str, Any]] = []
    for row, line in road_rows:
        width = float(row.get("width_m", 6.0) or 6.0)
        side_offset = max(width / 2.0 + offset_from_edge, offset_from_edge)
        for side in ("left", "right"):
            for shifted in offset_line_parts(line, side_offset, side):
                clipped = shifted.intersection(aoi)
                for segment in line_parts(clipped):
                    if segment.length < spacing * 0.5:
                        continue
                    distance = spacing * 0.5
                    while distance < segment.length:
                        point = segment.interpolate(distance)
                        if aoi.covers(point) and not (
                            clearance and any(point.distance(junction) < clearance for junction in junctions)
                        ):
                            candidates.append({
                                "x": float(point.x),
                                "y": float(point.y),
                                "source": "OSM road centerline-derived street tree layout",
                                "confidence": 0.45,
                                "kind": "roadside_tree",
                                "spacing_m": spacing,
                                "roadside_offset_from_edge_m": offset_from_edge,
                                "intersection_clearance_m": clearance,
                                "source_road_osm_id": row.get("osm_id", "na"),
                            })
                            if len(candidates) >= max_count:
                                return dedupe_tree_candidates(candidates, config.roadside_tree_merge_distance_m)
                        distance += spacing
    return dedupe_tree_candidates(candidates, config.roadside_tree_merge_distance_m)[:max_count]


def sample_tree_candidates(green: gpd.GeoDataFrame, aoi: Polygon, config: RunConfig) -> list[dict[str, Any]]:
    tree_kinds = {"tree_cover", "mangroves", "tree", "tree_row", "forest", "wood"}
    candidates: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()

    def add_candidate(point: Point, source: str, confidence: float, kind: str) -> None:
        if not aoi.covers(point):
            return
        key = (int(round(point.x / 2.0)), int(round(point.y / 2.0)))
        if key in seen:
            return
        seen.add(key)
        candidates.append({"x": float(point.x), "y": float(point.y), "source": source, "confidence": confidence, "kind": kind})

    if green.empty:
        return candidates
    for _, row in green.iterrows():
        geom = row.geometry.intersection(aoi)
        if geom.is_empty:
            continue
        kind = str(row.get("kind", ""))
        source = str(row.get("source", ""))
        confidence = float(row.get("confidence", 0.65) or 0.65)
        if geom.geom_type == "Point" and kind == "tree":
            add_candidate(geom, source, confidence, kind)
            continue
        if kind == "tree_row":
            for line in line_parts(geom):
                if line.length <= 0:
                    continue
                count = max(1, int(math.floor(line.length / 12.0)))
                for i in range(count + 1):
                    add_candidate(line.interpolate(min(line.length, i * 12.0)), source, confidence, kind)
            continue
        if kind not in tree_kinds:
            continue
        for poly in polygon_parts(geom):
            per_polygon_cap = max(1, min(20, int(math.ceil(poly.area / 45.0))))
            for point in sample_points_in_polygon(poly, spacing_m=7.5, max_points=per_polygon_cap):
                add_candidate(point, source, confidence, kind)
        if len(candidates) >= 180:
            break
    return candidates[:180]


def runs_from_mask(mask: np.ndarray, xs: np.ndarray, ys: np.ndarray, z_base: float | np.ndarray, z_top: float | np.ndarray,
                   layer: str, element_id: str, config: RunConfig, dem_surface: dict[str, Any] | None = None,
                   z_values_are_absolute: bool = False) -> list[dict[str, Any]]:
    """Convert a 2D mask to sparse voxel runs.

    Scalar z values are heights relative to the local DEM surface unless
    z_values_are_absolute is set. Array z values are treated as absolute
    elevations.
    """
    runs = []
    vs = config.voxel_size_m
    if mask.size == 0:
        return runs
    for iy, y in enumerate(ys):
        row = mask[iy]
        x_indices = np.where(row)[0]
        if len(x_indices) == 0:
            continue
        breaks = np.where(np.diff(x_indices) > 1)[0]
        starts = np.r_[x_indices[0], x_indices[breaks + 1]]
        ends = np.r_[x_indices[breaks], x_indices[-1]]
        for s, e in zip(starts, ends):
            x0 = float(xs[s] - vs / 2)
            x1 = float(xs[e] + vs / 2)
            y0 = float(y - vs / 2)
            y1 = float(y + vs / 2)
            cx = (x0 + x1) / 2
            cy = y
            local_terrain_z = float(terrain_z(cx, cy, config, dem_surface))
            if isinstance(z_base, np.ndarray):
                zb = float(z_base[iy, s])
            elif z_values_are_absolute:
                zb = float(z_base)
            else:
                zb = float(local_terrain_z + z_base)
            if isinstance(z_top, np.ndarray):
                zt = float(z_top[iy, s])
            elif z_values_are_absolute:
                zt = float(z_top)
            else:
                zt = float(local_terrain_z + z_top)
            if zt <= zb:
                zt = zb + vs
            vx = max(1, int(round((x1 - x0) / vs)))
            vz = max(1, int(math.ceil((zt - zb) / vs)))
            runs.append({
                "layer": layer, "element_id": element_id, "x_min": round(x0, 3), "x_max": round(x1, 3),
                "y_min": round(y0, 3), "y_max": round(y1, 3), "z_min": round(zb, 3), "z_max": round(zb + vz * vs, 3),
                "voxel_count": int(vx * vz), "voxel_size_m": vs,
            })
    return runs


def build_sparse_runs(local: dict[str, gpd.GeoDataFrame], config: RunConfig, dem_surface: dict[str, Any] | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    runs: list[dict[str, Any]] = []
    mappings: list[dict[str, Any]] = []
    aoi = box(-config.half_size_m, -config.half_size_m, config.half_size_m, config.half_size_m)
    layers = voxel_layer_names(config)
    has_worldcover_green = (
        "source" in local["green"].columns
        and local["green"]["source"].astype(str).str.contains("ESA WorldCover", case=False, na=False).any()
    )

    # Terrain as one-voxel-thick surface rows at the configured output resolution.
    vs = config.voxel_size_m
    xs = np.arange(-config.half_size_m + vs / 2, config.half_size_m, vs)
    ys = np.arange(-config.half_size_m + vs / 2, config.half_size_m, vs)
    for y in ys:
        # Chunk terrain by 8 m to keep Rhino object count tractable while preserving z by chunk midpoint.
        chunk = int(round(8.0 / vs))
        for start in range(0, len(xs), chunk):
            end = min(len(xs) - 1, start + chunk - 1)
            x0 = float(xs[start] - vs / 2)
            x1 = float(xs[end] + vs / 2)
            z = float(terrain_z((x0 + x1) / 2, y, config, dem_surface))
            runs.append({
                "layer": layers["terrain"], "element_id": terrain_element_id(config, dem_surface),
                "x_min": round(x0, 3), "x_max": round(x1, 3), "y_min": round(float(y - vs / 2), 3), "y_max": round(float(y + vs / 2), 3),
                "z_min": round(z - vs, 3), "z_max": round(z, 3), "voxel_count": int(round((x1 - x0) / vs)),
                "voxel_size_m": vs,
            })
    terrain_rule = "one-voxel-thick DEM surface from aws_terrarium" if is_real_dem(dem_surface) else "one-voxel-thick procedural terrain fallback; preview only"
    mappings.append({"element_type": "terrain", "element_id": terrain_element_id(config, dem_surface), "source": (dem_surface or {}).get("metadata", {}).get("source", ""), "confidence": 0.75 if is_real_dem(dem_surface) else 0.35, "layer": layers["terrain"], "voxelization_rule": terrain_rule})

    occupied_surface = []
    for _, row in local["buildings"].iterrows():
        geom = row.geometry.intersection(aoi)
        if geom.is_empty:
            continue
        for part_no, poly in enumerate(polygon_parts(geom)):
            xs2, ys2, mask = polygon_mask(poly, config)
            eid = f"building_{row.get('osm_id', 'na')}_{part_no}"
            base_eid = f"building_base_{row.get('osm_id', 'na')}_{part_no}"
            height = float(row.get("height_m", 12.0))
            anchor = building_anchor_point(poly)
            anchor_z = float(terrain_z(anchor.x, anchor.y, config, dem_surface))
            terrain_stats = terrain_stats_for_mask(mask, xs2, ys2, config, dem_surface)
            layer_runs = runs_from_mask(
                mask, xs2, ys2, anchor_z, anchor_z + height, layers["buildings"], eid, config, dem_surface,
                z_values_are_absolute=True,
            )
            runs.extend(layer_runs)
            if terrain_stats["min"] < anchor_z - config.voxel_size_m * 0.25:
                runs.extend(runs_from_mask(
                    mask, xs2, ys2, terrain_stats["min"], anchor_z, layers["building_bases"], base_eid, config,
                    dem_surface, z_values_are_absolute=True,
                ))
                mappings.append({
                    "element_type": "building_base", "element_id": base_eid, "source": row.get("source"),
                    "confidence": row.get("confidence"), "layer": layers["building_bases"],
                    "anchor_x_m": round(anchor.x, 3), "anchor_y_m": round(anchor.y, 3),
                    "anchor_terrain_z_m": round(anchor_z, 3), "footprint_terrain_min_m": round(terrain_stats["min"], 3),
                    "footprint_terrain_max_m": round(terrain_stats["max"], 3),
                    "voxelization_rule": "plinth slab from footprint terrain minimum to building anchor DEM elevation",
                })
            occupied_surface.append(poly)
            mappings.append({
                "element_type": "building", "element_id": eid, "source": row.get("source"),
                "confidence": row.get("confidence"), "layer": layers["buildings"],
                "anchor_x_m": round(anchor.x, 3), "anchor_y_m": round(anchor.y, 3),
                "anchor_terrain_z_m": round(anchor_z, 3), "footprint_terrain_min_m": round(terrain_stats["min"], 3),
                "footprint_terrain_mean_m": round(terrain_stats["mean"], 3), "footprint_terrain_max_m": round(terrain_stats["max"], 3),
                "height_m": round(height, 3),
                "voxelization_rule": "whole building footprint extruded from a single anchor DEM elevation to preserve white-box massing",
            })

    road_polys = []
    for _, row in local["roads"].iterrows():
        geom = row.geometry.intersection(aoi)
        if geom.is_empty:
            continue
        poly = geom.buffer(float(row.get("width_m", 6.0)) / 2.0, cap_style=2, join_style=2).intersection(aoi)
        if poly.is_empty:
            continue
        road_polys.append(poly)
        for part_no, part in enumerate(polygon_parts(poly)):
            xs2, ys2, mask = polygon_mask(part, config)
            eid = f"road_{row.get('osm_id', 'na')}_{part_no}"
            runs.extend(runs_from_mask(mask, xs2, ys2, 0.0, 0.0, layers["roads"], eid, config, dem_surface))
            mappings.append({"element_type": "road", "element_id": eid, "source": row.get("source"), "confidence": row.get("confidence"), "layer": layers["roads"], "voxelization_rule": "centerline buffered by width_m and rasterized as one hardscape surface voxel"})

    for dataset, layer, etype in [("water", layers["water"], "water"), ("green", layers["grass"], "green")]:
        for _, row in local[dataset].iterrows():
            geom = row.geometry.intersection(aoi)
            if geom.is_empty:
                continue
            for part_no, poly in enumerate(polygon_parts(geom)):
                xs2, ys2, mask = polygon_mask(poly, config)
                eid = f"{etype}_{row.get('osm_id', 'na')}_{part_no}"
                runs.extend(runs_from_mask(mask, xs2, ys2, 0.0, 0.0, layer, eid, config, dem_surface))
                mappings.append({"element_type": etype, "element_id": eid, "source": row.get("source"), "confidence": row.get("confidence"), "layer": layer, "voxelization_rule": "polygon rasterized as one surface voxel"})

    # Grass fallback covers remaining AOI surface only when no WorldCover land-cover raster is available.
    exclusions = [g for g in occupied_surface + road_polys if not g.is_empty]
    residual = aoi.difference(unary_union(exclusions)) if exclusions else aoi
    if not has_worldcover_green and not residual.is_empty:
        parts = [residual] if residual.geom_type == "Polygon" else list(residual.geoms)
        for i, part in enumerate(parts):
            xs2, ys2, mask = polygon_mask(part, config)
            runs.extend(runs_from_mask(mask, xs2, ys2, 0.0, 0.0, layers["grass"], f"grass_residual_{i}", config, dem_surface))
        mappings.append({"element_type": "green", "element_id": "grass_residual", "source": "procedural fallback", "confidence": 0.35, "layer": layers["grass"], "voxelization_rule": "remaining AOI surface assigned to grass/ground cover fallback"})

    # Tree canopy markers are derived from source vegetation. When WorldCover is active,
    # do not fill missing trees with deterministic placeholders.
    rng = np.random.default_rng(config.random_seed)
    candidate_points = sample_tree_candidates(local["green"], aoi, config)
    roadside_candidates = sample_roadside_tree_candidates(local["roads"], aoi, config)
    if roadside_candidates:
        candidate_points.extend(roadside_candidates)
    if occupied_surface:
        building_obstacles = unary_union([geom for geom in occupied_surface if not geom.is_empty]).buffer(max(0.5, config.voxel_size_m * 0.5))
        candidate_points = [
            candidate for candidate in candidate_points
            if not building_obstacles.covers(Point(float(candidate["x"]), float(candidate["y"])))
        ]
    candidate_points = dedupe_tree_candidates(candidate_points, config.roadside_tree_merge_distance_m)
    while not has_worldcover_green and len(candidate_points) < 12:
        candidate_points.append({
            "x": float(rng.uniform(-config.half_size_m * 0.8, config.half_size_m * 0.8)),
            "y": float(rng.uniform(-config.half_size_m * 0.8, config.half_size_m * 0.8)),
            "source": "deterministic fallback", "confidence": 0.35, "kind": "fallback_tree",
        })
    for i, candidate in enumerate(candidate_points):
        cx = float(candidate["x"])
        cy = float(candidate["y"])
        kind = str(candidate.get("kind", "tree"))
        radius_min, radius_max = (1.5, 2.8) if kind in {"tree", "tree_row", "roadside_tree"} else (2.2, 3.6)
        height_min, height_max = (3.0, 5.5) if kind in {"tree", "tree_row", "roadside_tree"} else (3.5, 6.5)
        canopy = Point(cx, cy).buffer(float(rng.uniform(radius_min, radius_max)))
        xs2, ys2, mask = polygon_mask(canopy.intersection(aoi), config)
        zbase = 2.0
        ztop = zbase + float(rng.uniform(height_min, height_max))
        runs.extend(runs_from_mask(mask, xs2, ys2, zbase, ztop, layers["trees"], f"tree_canopy_{i:03d}", config, dem_surface))
    if candidate_points:
        sources = sorted({str(candidate.get("source", "")) for candidate in candidate_points if str(candidate.get("source", ""))})
        confidences = [float(candidate.get("confidence", 0.6) or 0.6) for candidate in candidate_points]
        kinds = pd.Series([str(candidate.get("kind", "tree")) for candidate in candidate_points]).value_counts().to_dict()
        mappings.append({
            "element_type": "tree", "element_id": "tree_canopy_samples",
            "source": "; ".join(sources), "confidence": round(float(np.nanmean(confidences)), 3),
            "layer": layers["trees"],
            "candidate_count": len(candidate_points),
            "candidate_kind_counts": json.dumps(kinds, ensure_ascii=True, sort_keys=True),
            "roadside_tree_spacing_m": config.roadside_tree_spacing_m,
            "roadside_tree_offset_m": config.roadside_tree_offset_m,
            "roadside_tree_intersection_clearance_m": config.roadside_tree_intersection_clearance_m,
            "roadside_tree_merge_distance_m": config.roadside_tree_merge_distance_m,
            "voxelization_rule": "tree canopy volumes sampled from ESA WorldCover tree polygons, retained OSM tree/tree_row features, and optional road-centerline-derived street-tree layout",
        })

    return pd.DataFrame(runs), pd.DataFrame(mappings)


MORPHOLOGY_FORMULAS: dict[str, str] = {
    "building_coverage_ratio": "BCR = A_building_footprint / A_AOI",
    "building_density_count_per_ha": "BD_ha = N_buildings / (A_AOI / 10000)",
    "floor_area_ratio_est": "FAR_est = sum(A_footprint_i * floors_i_est) / A_AOI, floors_i_est = max(1, height_i / 3.3)",
    "open_space_ratio": "OSR = 1 - BCR",
    "road_density_km_per_km2": "RD = (L_road / 1000) / (A_AOI / 1000000)",
    "impervious_surface_ratio": "ISR_proxy = min(1, (A_building_footprint + A_road_surface) / A_AOI)",
    "green_ratio": "GR = A_green / A_AOI",
    "terrain_relief_m": "Relief = max(DEM_z) - min(DEM_z)",
    "terrain_slope_proxy": "Slope_proxy = Relief / diagonal(AOI)",
    "sky_view_factor_proxy": "SVF_proxy = cos(arctan(H_mean / W_open_proxy)), W_open_proxy = sqrt((A_AOI - A_building_footprint) / max(N_buildings, 1))",
}


def _safe_gdf_area(gdf: gpd.GeoDataFrame | None) -> float:
    if gdf is None or gdf.empty:
        return 0.0
    return float(gdf.geometry.area.sum())


def _safe_gdf_length(gdf: gpd.GeoDataFrame | None) -> float:
    if gdf is None or gdf.empty:
        return 0.0
    return float(gdf.geometry.length.sum())


def compute_road_surface_area(roads: gpd.GeoDataFrame | None, aoi: Polygon) -> float:
    if roads is None or roads.empty:
        return 0.0
    road_polys = []
    for _, row in roads.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        buffered = geom.buffer(float(row.get("width_m", 6.0) or 6.0) / 2.0, cap_style=2, join_style=2).intersection(aoi)
        if not buffered.is_empty:
            road_polys.append(buffered)
    return float(unary_union(road_polys).area) if road_polys else 0.0


def estimate_floor_area(buildings: gpd.GeoDataFrame | None) -> float:
    if buildings is None or buildings.empty:
        return 0.0
    total = 0.0
    for _, row in buildings.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        height = float(row.get("height_m", 0.0) or 0.0)
        floors = row.get("floors", None)
        try:
            floor_count = float(floors)
        except (TypeError, ValueError):
            floor_count = 0.0
        if not math.isfinite(floor_count) or floor_count <= 0:
            floor_count = max(1.0, height / 3.3) if height > 0 else 1.0
        total += float(geom.area) * floor_count
    return total


def tree_and_grass_area(green: gpd.GeoDataFrame | None) -> tuple[float, float]:
    if green is None or green.empty:
        return 0.0, 0.0
    tree_area = 0.0
    grass_area = 0.0
    for _, row in green.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        kind = str(row.get("kind", "")).lower()
        if "tree" in kind or "forest" in kind or "wood" in kind:
            tree_area += float(geom.area)
        else:
            grass_area += float(geom.area)
    return tree_area, grass_area


def compute_scene_morphology_indicators(
    local: dict[str, gpd.GeoDataFrame],
    config: RunConfig,
    dem_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    aoi = box(-config.half_size_m, -config.half_size_m, config.half_size_m, config.half_size_m)
    aoi_area = (config.half_size_m * 2.0) ** 2
    buildings = local.get("buildings")
    roads = local.get("roads")
    green = local.get("green")
    water = local.get("water")
    building_area = _safe_gdf_area(buildings)
    road_area = compute_road_surface_area(roads, aoi)
    green_area = _safe_gdf_area(green)
    water_area = _safe_gdf_area(water)
    tree_area, grass_area = tree_and_grass_area(green)
    building_count = int(len(buildings)) if buildings is not None else 0
    road_length = _safe_gdf_length(roads)
    height_series = (
        pd.to_numeric(buildings.get("height_m", pd.Series(dtype=float)), errors="coerce").dropna()
        if buildings is not None and not buildings.empty
        else pd.Series(dtype=float)
    )
    height_mean = float(height_series.mean()) if not height_series.empty else 0.0
    height_min = float(height_series.min()) if not height_series.empty else 0.0
    height_max = float(height_series.max()) if not height_series.empty else 0.0
    height_std = float(height_series.std(ddof=0)) if len(height_series) > 1 else 0.0
    floor_area = estimate_floor_area(buildings)
    open_area = max(0.0, aoi_area - building_area)
    open_width_proxy = math.sqrt(open_area / max(building_count, 1)) if aoi_area else 0.0
    height_to_open_width_proxy = height_mean / max(open_width_proxy, 1e-9) if open_width_proxy else 0.0
    svf_proxy = float(math.cos(math.atan(height_to_open_width_proxy))) if open_width_proxy else 1.0
    dem_meta = (dem_surface or {}).get("metadata", {})
    terrain_relief = float(dem_meta.get("elevation_range_m") or 0.0)
    aoi_diagonal = math.hypot(config.half_size_m * 2.0, config.half_size_m * 2.0)
    morphology = {
        "pipeline_version": PIPELINE_VERSION,
        "aoi_area_m2": round(aoi_area, 3),
        "building_count": building_count,
        "building_footprint_area_m2": round(building_area, 3),
        "building_coverage_ratio": round(building_area / aoi_area if aoi_area else 0.0, 4),
        "building_density_count_per_ha": round(building_count / (aoi_area / 10_000.0), 4) if aoi_area else 0.0,
        "building_density_count_per_km2": round(building_count / (aoi_area / 1_000_000.0), 4) if aoi_area else 0.0,
        "building_height_min_m": round(height_min, 3),
        "building_height_mean_m": round(height_mean, 3),
        "building_height_max_m": round(height_max, 3),
        "building_height_std_m": round(height_std, 3),
        "building_floor_area_est_m2": round(floor_area, 3),
        "floor_area_ratio_est": round(floor_area / aoi_area if aoi_area else 0.0, 4),
        "open_space_ratio": round(max(0.0, 1.0 - building_area / aoi_area) if aoi_area else 0.0, 4),
        "open_width_proxy_m": round(open_width_proxy, 3),
        "height_to_open_width_proxy": round(height_to_open_width_proxy, 4),
        "sky_view_factor_proxy": round(max(0.0, min(1.0, svf_proxy)), 4),
        "road_centerline_length_m": round(road_length, 3),
        "road_surface_area_m2": round(road_area, 3),
        "road_density_km_per_km2": round((road_length / 1000.0) / (aoi_area / 1_000_000.0), 3) if aoi_area else 0.0,
        "impervious_surface_ratio": round(min(1.0, (building_area + road_area) / aoi_area), 4) if aoi_area else 0.0,
        "green_area_m2": round(green_area, 3),
        "green_ratio": round(green_area / aoi_area if aoi_area else 0.0, 4),
        "tree_cover_area_m2": round(tree_area, 3),
        "tree_cover_ratio": round(tree_area / aoi_area if aoi_area else 0.0, 4),
        "grass_area_m2": round(grass_area, 3),
        "grass_ratio": round(grass_area / aoi_area if aoi_area else 0.0, 4),
        "water_area_m2": round(water_area, 3),
        "water_ratio": round(water_area / aoi_area if aoi_area else 0.0, 4),
        "blue_green_ratio": round(min(1.0, (green_area + water_area) / aoi_area), 4) if aoi_area else 0.0,
        "terrain_elevation_min_m": dem_meta.get("min_elevation_m"),
        "terrain_elevation_mean_m": dem_meta.get("mean_elevation_m"),
        "terrain_elevation_max_m": dem_meta.get("max_elevation_m"),
        "terrain_relief_m": round(terrain_relief, 3),
        "terrain_slope_proxy": round(terrain_relief / max(aoi_diagonal, 1.0), 4),
    }
    return morphology


def load_scene_lcz_config() -> dict[str, Any]:
    path = PROJECT_ROOT / "config" / "lcz_thresholds.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {
        "rule_order": [],
        "default_lcz": "LCZ 9 - Sparsely built",
    }


def classify_scene_from_morphology(morphology: dict[str, Any]) -> dict[str, Any]:
    def morph_float(field: str, default: float = math.nan) -> float:
        try:
            return float(morphology.get(field, default))
        except (TypeError, ValueError):
            return default

    lcz_config = load_scene_lcz_config()
    primary = str(lcz_config.get("default_lcz", "LCZ 9 - Sparsely built"))
    confidence = 0.45
    reasons = ["No explicit LCZ rule matched; default fallback."]
    matched_rule = None
    for rule in lcz_config.get("rule_order", []):
        rule_reasons = []
        ok = True
        for field, bounds in rule.get("conditions", {}).items():
            value = morph_float(field)
            lo, hi = float(bounds[0]), float(bounds[1])
            if not math.isfinite(value) or value < lo or value > hi:
                ok = False
                break
            rule_reasons.append(f"{field}={value:.3f} in [{lo:g}, {hi:g}]")
        if ok:
            primary = str(rule.get("lcz", primary))
            confidence = float(rule.get("confidence", confidence))
            reasons = rule_reasons
            matched_rule = rule
            break

    alternatives = [
        str(rule.get("lcz"))
        for rule in lcz_config.get("rule_order", [])
        if rule is not matched_rule and str(rule.get("lcz")) != primary
    ][:2]
    if not alternatives:
        alternatives = ["LCZ 5 - Open mid-rise", "LCZ 6 - Open low-rise"]

    building_fraction = morph_float("building_coverage_ratio", 0.0)
    impervious_fraction = morph_float("impervious_surface_ratio", 0.0)
    green_fraction = morph_float("green_ratio", 0.0)
    terrain_relief = morph_float("terrain_relief_m", 0.0)
    if impervious_fraction >= 0.45 and building_fraction >= 0.20:
        alcc_type = "urban_core_hardscape_built_environment"
    elif building_fraction >= 0.10 and green_fraction >= 0.10:
        alcc_type = "mixed_open_built_green_environment"
    elif green_fraction >= 0.35:
        alcc_type = "urban_green_open_space"
    elif building_fraction >= 0.10:
        alcc_type = "sparse_built_environment"
    else:
        alcc_type = "low_density_open_environment"

    if terrain_relief >= 25:
        reasons.append("Terrain relief >= 25 m; treat LCZ as a morphology class with terrain qualifier.")
    return {
        "lcz_primary": primary,
        "lcz_alternatives": alternatives,
        "lcz_confidence": round(confidence, 3),
        "alcc_type": alcc_type,
        "rationale": reasons,
        "method_note": "Rule-based scene LCZ/ALCC estimate from generated real-data morphology metrics; calibrate before publication claims.",
    }


def morphology_info_text_lines(config: RunConfig, morphology: dict[str, Any], classification: dict[str, Any]) -> list[str]:
    site_label = config.site_name_cn or config.site_name
    return [
        f"Model: {site_label}",
        f"Version: v{PIPELINE_VERSION}; AOI: {config.half_size_m * 2:g}m x {config.half_size_m * 2:g}m; voxel: {config.voxel_size_m:g}m",
        f"LCZ: {classification.get('lcz_primary')} (confidence={classification.get('lcz_confidence')}); ALCC: {classification.get('alcc_type')}",
        f"H_mean={morphology.get('building_height_mean_m')}m; H_max={morphology.get('building_height_max_m')}m; N_buildings={morphology.get('building_count')}",
        f"BCR=A_building/A_AOI={morphology.get('building_coverage_ratio')}; BD={morphology.get('building_density_count_per_ha')} buildings/ha",
        f"FAR_est=sum(A_i*floors_i)/A_AOI={morphology.get('floor_area_ratio_est')}; floors_i=max(1,height_i/3.3)",
        f"SVF_proxy=cos(atan(H_mean/W_open))={morphology.get('sky_view_factor_proxy')}; W_open={morphology.get('open_width_proxy_m')}m",
        f"Green={morphology.get('green_ratio')}; tree_cover={morphology.get('tree_cover_ratio')}; impervious={morphology.get('impervious_surface_ratio')}",
        f"Road density={morphology.get('road_density_km_per_km2')} km/km2; DEM relief={morphology.get('terrain_relief_m')}m",
    ]


def geographic_coordinate_info_entries(config: RunConfig, dem_surface: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    half = float(config.half_size_m)
    bbox = bbox_lonlat(config)
    center_z = float(terrain_z(0.0, 0.0, config, dem_surface))
    entries: list[dict[str, Any]] = [
        {
            "id": "center",
            "text": f"Center WGS84: lon={config.center_lon:.8f}, lat={config.center_lat:.8f}, z={center_z:.2f}m",
            "x": 0.0,
            "y": 0.0,
            "z": center_z + 2.0,
        },
        {
            "id": "bbox",
            "text": (
                f"AOI bbox WGS84: W={bbox['west']:.8f}, S={bbox['south']:.8f}, "
                f"E={bbox['east']:.8f}, N={bbox['north']:.8f}"
            ),
            "x": -half,
            "y": -half - 16.0,
            "z": 0.0,
        },
        {
            "id": "local_axes",
            "text": "Local model axes: X=east m, Y=north m, Z=elevation m; origin=AOI center WGS84",
            "x": -half,
            "y": -half - 23.0,
            "z": 0.0,
        },
        {
            "id": "model_size",
            "text": f"Model extent: {half * 2:g}m x {half * 2:g}m; voxel={config.voxel_size_m:g}m",
            "x": -half,
            "y": -half - 30.0,
            "z": 0.0,
        },
    ]
    corners = [
        ("SW", -half, -half),
        ("NW", -half, half),
        ("NE", half, half),
        ("SE", half, -half),
    ]
    for label, x, y in corners:
        lon, lat = lonlat_from_xy(x, y, config.center_lon, config.center_lat)
        z = float(terrain_z(x, y, config, dem_surface))
        entries.append({
            "id": f"corner_{label.lower()}",
            "text": f"{label}: lon={lon:.8f}, lat={lat:.8f}, local=({x:.1f},{y:.1f}), z={z:.2f}m",
            "x": x,
            "y": y,
            "z": z + 2.0,
        })
    return entries


def set_clean_mesh_display(attr: rhino3dm.ObjectAttributes, config: RunConfig) -> bool:
    if not config.rhino_clean_mesh_wire_display:
        return False
    try:
        attr.WireDensity = -1
        return True
    except Exception:
        return False


def add_box(mesh: rhino3dm.Mesh, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> None:
    base = len(mesh.Vertices)
    pts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    for p in pts:
        mesh.Vertices.Add(*map(float, p))
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    for a, b, c, d in faces:
        mesh.Faces.AddFace(base + a, base + b, base + c, base + d)


def add_quad(mesh: rhino3dm.Mesh, points: list[tuple[float, float, float]]) -> None:
    if len(points) != 4:
        raise ValueError("add_quad expects exactly four points")
    base = len(mesh.Vertices)
    for point in points:
        mesh.Vertices.Add(float(point[0]), float(point[1]), float(point[2]))
    mesh.Faces.AddFace(base, base + 1, base + 2, base + 3)


def add_run_top_bottom_faces(mesh: rhino3dm.Mesh, row: dict[str, Any], z0: float, z1: float) -> None:
    x0 = float(row["x_min"])
    x1 = float(row["x_max"])
    y0 = float(row["y_min"])
    y1 = float(row["y_max"])
    add_quad(mesh, [(x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)])
    add_quad(mesh, [(x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0)])


def add_vertical_sides_for_ring(mesh: rhino3dm.Mesh, coords: Iterable[tuple[float, float]], z0: float, z1: float) -> int:
    points = [(float(x), float(y)) for x, y in coords]
    if len(points) < 2:
        return 0
    face_count = 0
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:]):
        if abs(x0 - x1) < 1e-9 and abs(y0 - y1) < 1e-9:
            continue
        add_quad(mesh, [(x0, y0, z0), (x1, y1, z0), (x1, y1, z1), (x0, y0, z1)])
        face_count += 1
    return face_count


def add_merged_run_shell(mesh: rhino3dm.Mesh, rows: list[dict[str, Any]]) -> bool:
    """Build one voxel-outline shell from run rectangles when all rows share a z span."""
    if not rows:
        return False
    z_mins = [float(row["z_min"]) for row in rows]
    z_maxs = [float(row["z_max"]) for row in rows]
    z0 = min(z_mins)
    z1 = max(z_maxs)
    if max(z_mins) - z0 > 1e-6 or z1 - min(z_maxs) > 1e-6:
        return False
    try:
        rects = [
            box(float(row["x_min"]), float(row["y_min"]), float(row["x_max"]), float(row["y_max"]))
            for row in rows
        ]
        footprint = unary_union(rects)
    except Exception:
        return False
    if footprint.is_empty:
        return False
    for row in rows:
        add_run_top_bottom_faces(mesh, row, z0, z1)
    side_face_count = 0
    for poly in polygon_parts(footprint):
        side_face_count += add_vertical_sides_for_ring(mesh, poly.exterior.coords, z0, z1)
        for interior in poly.interiors:
            side_face_count += add_vertical_sides_for_ring(mesh, interior.coords, z0, z1)
    return side_face_count > 0


def add_run_as_unit_voxel_boxes(mesh: rhino3dm.Mesh, row: dict[str, Any], voxel_size_m: float) -> int:
    vs = float(voxel_size_m)
    nx = max(1, int(round((float(row["x_max"]) - float(row["x_min"])) / vs)))
    ny = max(1, int(round((float(row["y_max"]) - float(row["y_min"])) / vs)))
    nz = max(1, int(round((float(row["z_max"]) - float(row["z_min"])) / vs)))
    count = 0
    for ix in range(nx):
        x0 = float(row["x_min"]) + ix * vs
        x1 = min(float(row["x_max"]), x0 + vs)
        for iy in range(ny):
            y0 = float(row["y_min"]) + iy * vs
            y1 = min(float(row["y_max"]), y0 + vs)
            for iz in range(nz):
                z0 = float(row["z_min"]) + iz * vs
                z1 = min(float(row["z_max"]), z0 + vs)
                add_box(mesh, x0, x1, y0, y1, z0, z1)
                count += 1
    return count


def building_group_key(element_id: str) -> str:
    if element_id.startswith("building_base_"):
        return "building_" + element_id[len("building_base_"):]
    if element_id.startswith("building_"):
        return element_id
    return ""


def ensure_rhino_group(model: rhino3dm.File3dm, group_name: str) -> int:
    existing = model.Groups.FindName(group_name)
    if existing is not None:
        return int(existing.Index)
    group = rhino3dm.Group()
    group.Name = group_name
    model.Groups.Add(group)
    created = model.Groups.FindName(group_name)
    return int(created.Index) if created is not None else len(model.Groups) - 1


def export_rhino(runs: pd.DataFrame, mappings: pd.DataFrame, config: RunConfig, dirs: dict[str, Path],
                 local: dict[str, gpd.GeoDataFrame] | None = None,
                 dem_surface: dict[str, Any] | None = None) -> dict[str, Any]:
    model = rhino3dm.File3dm()
    model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters
    layer_indices = {}
    layer_rows = []
    colors = layer_color_map(config)
    layers = voxel_layer_names(config)
    for name in sorted(set(runs["layer"].astype(str)).union(colors.keys())):
        rgba = colors.get(name, (180, 180, 180, 255))
        layer = rhino3dm.Layer()
        layer.Name = name
        layer.Color = rgba
        layer_indices[name] = model.Layers.Add(layer)
        layer_rows.append({"layer": name, "r": rgba[0], "g": rgba[1], "b": rgba[2], "a": rgba[3], "unit": "meter"})

    object_rows = []
    object_count = 0
    building_layers = {layers["buildings"], layers["building_bases"]}
    handled_indices: set[int] = set()
    building_group_count = 0
    building_mesh_count = 0
    building_unit_voxel_box_count = 0
    component_mesh_object_count = 0
    clean_mesh_wire_object_count = 0
    topology_clean_mesh_object_count = 0
    unit_voxel_fallback_reason = ""
    building_voxel_total = int(
        runs.loc[runs["layer"] == layers["buildings"], "voxel_count"].sum()
    ) if not runs.empty else 0
    expand_building_voxels = (
        config.rhino_export_mode == "building_voxel_groups"
        and config.voxel_size_m >= 1.0
        and building_voxel_total <= config.rhino_unit_voxel_max_boxes
    )
    if config.rhino_export_mode == "building_voxel_groups" and not expand_building_voxels:
        if config.voxel_size_m < 1.0:
            unit_voxel_fallback_reason = "Building unit-voxel Rhino expansion is disabled below 1 m to avoid oversized 3DM files."
        elif building_voxel_total > config.rhino_unit_voxel_max_boxes:
            unit_voxel_fallback_reason = (
                f"Building voxel count {building_voxel_total} exceeds rhino_unit_voxel_max_boxes "
                f"{config.rhino_unit_voxel_max_boxes}; exported as grouped run-length meshes."
            )

    def add_grouped_building_mesh(
        mesh: rhino3dm.Mesh,
        layer: str,
        element_id: Any,
        group_name: str,
        group_index: int,
        run_count: int,
        voxel_count: int,
        expanded_boxes: int,
        chunk_no: int | None = None,
        topology_clean_shell: bool = False,
    ) -> None:
        nonlocal object_count, building_mesh_count, building_unit_voxel_box_count
        nonlocal clean_mesh_wire_object_count, topology_clean_mesh_object_count
        mesh.Compact()
        attr = rhino3dm.ObjectAttributes()
        attr.LayerIndex = layer_indices[layer]
        suffix = "unit_voxels" if expanded_boxes else "clean_shell" if topology_clean_shell else "runs"
        if chunk_no is not None:
            suffix = f"{suffix}_chunk_{chunk_no:03d}"
        attr.Name = safe_filename(f"{element_id}_{suffix}")
        attr.ColorSource = rhino3dm.ObjectColorSource.ColorFromLayer
        attr.AddToGroup(group_index)
        clean_wire_display = set_clean_mesh_display(attr, config)
        model.Objects.AddMesh(mesh, attr)
        object_count += 1
        building_mesh_count += 1
        building_unit_voxel_box_count += expanded_boxes
        if clean_wire_display:
            clean_mesh_wire_object_count += 1
        if topology_clean_shell:
            topology_clean_mesh_object_count += 1
        object_rows.append({
            "object_name": attr.Name,
            "layer": layer,
            "geometry_type": "mesh",
            "element_id": element_id,
            "group_name": group_name,
            "group_index": group_index,
            "run_start": "",
            "run_count": int(run_count),
            "voxel_count": int(voxel_count),
            "unit_voxel_boxes_exported": int(expanded_boxes),
            "topology_clean_shell": bool(topology_clean_shell),
            "clean_mesh_wire_display": bool(clean_wire_display),
        })

    if config.group_buildings_in_rhino and not runs.empty:
        building_runs = runs[runs["layer"].isin(building_layers)]
        seen_group_keys: set[str] = set()
        for (layer, element_id), element_group in building_runs.groupby(["layer", "element_id"], dropna=False):
            group_key = building_group_key(str(element_id))
            if not group_key:
                continue
            group_name = safe_filename(f"{config.site_name}_{group_key}")
            group_index = ensure_rhino_group(model, group_name)
            seen_group_keys.add(group_key)
            subset = element_group.to_dict("records")
            if layer == layers["buildings"] and expand_building_voxels:
                chunk_cap = max(1, int(config.rhino_unit_voxel_mesh_chunk_boxes))
                mesh = rhino3dm.Mesh()
                expanded_boxes = 0
                chunk_run_count = 0
                chunk_voxel_count = 0
                chunk_no = 0
                for r in subset:
                    row_voxel_count = int(r.get("voxel_count", 0) or 0)
                    if expanded_boxes and expanded_boxes + row_voxel_count > chunk_cap:
                        add_grouped_building_mesh(
                            mesh, layer, element_id, group_name, group_index,
                            chunk_run_count, chunk_voxel_count, expanded_boxes, chunk_no,
                        )
                        chunk_no += 1
                        mesh = rhino3dm.Mesh()
                        expanded_boxes = 0
                        chunk_run_count = 0
                        chunk_voxel_count = 0
                    expanded_boxes += add_run_as_unit_voxel_boxes(mesh, r, config.voxel_size_m)
                    chunk_run_count += 1
                    chunk_voxel_count += row_voxel_count
                if chunk_run_count:
                    add_grouped_building_mesh(
                        mesh, layer, element_id, group_name, group_index,
                        chunk_run_count, chunk_voxel_count, expanded_boxes, chunk_no,
                    )
            else:
                mesh = rhino3dm.Mesh()
                topology_clean_shell = add_merged_run_shell(mesh, subset)
                if not topology_clean_shell:
                    mesh = rhino3dm.Mesh()
                    for r in subset:
                        add_box(mesh, r["x_min"], r["x_max"], r["y_min"], r["y_max"], r["z_min"], r["z_max"])
                add_grouped_building_mesh(
                    mesh, layer, element_id, group_name, group_index,
                    len(subset), int(sum(r["voxel_count"] for r in subset)), 0, None, topology_clean_shell,
                )
            handled_indices.update(element_group.index.astype(int).tolist())
        building_group_count = len(seen_group_keys)

    remaining_runs = runs.drop(index=list(handled_indices)) if handled_indices else runs
    remaining_chunk_size = (
        max(1, int(config.rhino_component_mesh_max_runs))
        if config.rhino_export_mode == "component_mesh_groups"
        else 3500
    )
    for layer, group in remaining_runs.groupby("layer"):
        rows = group.to_dict("records")
        for chunk_no in range(0, len(rows), remaining_chunk_size):
            mesh = rhino3dm.Mesh()
            subset = rows[chunk_no:chunk_no + remaining_chunk_size]
            for r in subset:
                add_box(mesh, r["x_min"], r["x_max"], r["y_min"], r["y_max"], r["z_min"], r["z_max"])
            mesh.Compact()
            attr = rhino3dm.ObjectAttributes()
            attr.LayerIndex = layer_indices[layer]
            chunk_index = chunk_no // remaining_chunk_size
            if config.rhino_export_mode == "component_mesh_groups":
                suffix = "" if len(rows) <= remaining_chunk_size else f"_chunk_{chunk_index:04d}"
                attr.Name = safe_filename(f"{layer}_component_mesh{suffix}")
            else:
                attr.Name = f"{layer}_chunk_{chunk_index:04d}"
            attr.ColorSource = rhino3dm.ObjectColorSource.ColorFromLayer
            clean_wire_display = set_clean_mesh_display(attr, config)
            model.Objects.AddMesh(mesh, attr)
            object_count += 1
            component_mesh_object_count += 1
            if clean_wire_display:
                clean_mesh_wire_object_count += 1
            object_rows.append({
                "object_name": attr.Name,
                "layer": layer,
                "geometry_type": "mesh",
                "export_strategy": "component_mesh" if config.rhino_export_mode == "component_mesh_groups" else "layer_chunk_mesh",
                "run_start": chunk_no,
                "run_count": len(subset),
                "voxel_count": int(sum(r["voxel_count"] for r in subset)),
                "topology_clean_shell": False,
                "clean_mesh_wire_display": bool(clean_wire_display),
            })

    # AOI boundary.
    half = config.half_size_m
    boundary = rhino3dm.PolylineCurve([
        rhino3dm.Point3d(-half, -half, 0),
        rhino3dm.Point3d(half, -half, 0),
        rhino3dm.Point3d(half, half, 0),
        rhino3dm.Point3d(-half, half, 0),
        rhino3dm.Point3d(-half, -half, 0),
    ])
    attr = rhino3dm.ObjectAttributes()
    attr.LayerIndex = layer_indices[layers["aoi"]]
    attr.Name = "AOI_boundary_meter"
    attr.ColorSource = rhino3dm.ObjectColorSource.ColorFromLayer
    model.Objects.AddCurve(boundary, attr)
    object_count += 1
    object_rows.append({"object_name": attr.Name, "layer": layers["aoi"], "geometry_type": "curve", "run_start": "", "run_count": 0, "voxel_count": 0})

    road_centerline_curve_count = 0
    if local is not None and "roads" in local and not local["roads"].empty:
        aoi = box(-config.half_size_m, -config.half_size_m, config.half_size_m, config.half_size_m)
        for _, row in local["roads"].iterrows():
            geom = row.geometry.intersection(aoi)
            for part_no, line in enumerate(line_parts(geom)):
                coords = list(line.coords)
                if len(coords) < 2:
                    continue
                points = [
                    rhino3dm.Point3d(float(x), float(y), float(terrain_z(float(x), float(y), config, dem_surface)) + 0.15)
                    for x, y in coords
                ]
                curve = rhino3dm.PolylineCurve(points)
                attr = rhino3dm.ObjectAttributes()
                attr.LayerIndex = layer_indices[layers["road_centerlines"]]
                attr.Name = f"road_centerline_{row.get('osm_id', 'na')}_{part_no}"
                attr.ColorSource = rhino3dm.ObjectColorSource.ColorFromLayer
                model.Objects.AddCurve(curve, attr)
                object_count += 1
                road_centerline_curve_count += 1
                object_rows.append({
                    "object_name": attr.Name, "layer": layers["road_centerlines"], "geometry_type": "curve",
                    "run_start": "", "run_count": 0, "voxel_count": 0, "source": row.get("source"),
                    "osm_id": row.get("osm_id", "na"),
                })

    lcz_info_text_count = 0
    if config.lcz_info_text_enabled and local is not None:
        morphology = compute_scene_morphology_indicators(local, config, dem_surface)
        scene_classification = classify_scene_from_morphology(morphology)
        for line_no, text in enumerate(morphology_info_text_lines(config, morphology, scene_classification)):
            dot_point = rhino3dm.Point3d(-half, -half - 16.0 - line_no * 7.0, 0.0)
            attr = rhino3dm.ObjectAttributes()
            attr.LayerIndex = layer_indices[layers["lcz_info"]]
            attr.Name = safe_filename(f"lcz_morphology_info_{line_no:02d}")
            attr.ColorSource = rhino3dm.ObjectColorSource.ColorFromLayer
            model.Objects.AddTextDot(str(text), dot_point, attr)
            object_count += 1
            lcz_info_text_count += 1
            object_rows.append({
                "object_name": attr.Name,
                "layer": layers["lcz_info"],
                "geometry_type": "textdot",
                "run_start": "",
                "run_count": 0,
                "voxel_count": 0,
                "text": str(text),
            })

    geo_info_text_count = 0
    if config.rhino_geo_info_text_enabled:
        for entry in geographic_coordinate_info_entries(config, dem_surface):
            dot_point = rhino3dm.Point3d(float(entry["x"]), float(entry["y"]), float(entry["z"]))
            attr = rhino3dm.ObjectAttributes()
            attr.LayerIndex = layer_indices[layers["geo_info"]]
            attr.Name = safe_filename(f"geo_coordinate_info_{entry['id']}")
            attr.ColorSource = rhino3dm.ObjectColorSource.ColorFromLayer
            model.Objects.AddTextDot(str(entry["text"]), dot_point, attr)
            object_count += 1
            geo_info_text_count += 1
            object_rows.append({
                "object_name": attr.Name,
                "layer": layers["geo_info"],
                "geometry_type": "textdot",
                "run_start": "",
                "run_count": 0,
                "voxel_count": 0,
                "text": str(entry["text"]),
                "local_x_m": float(entry["x"]),
                "local_y_m": float(entry["y"]),
                "local_z_m": float(entry["z"]),
            })

    output_base = rhino_output_base(config)
    path = dirs["rhino"] / f"{output_base}.3dm"
    tmp_path = dirs["rhino"] / f"{output_base}.tmp.3dm"
    if tmp_path.exists():
        tmp_path.unlink()
    write_ok = model.Write(str(tmp_path), config.rhino_version)
    if not write_ok or not tmp_path.exists():
        raise RuntimeError(f"Failed to write Rhino 3DM temporary file: {tmp_path}")
    active_path = path
    target_replace_status = "replaced"
    target_replace_error = ""
    try:
        tmp_path.replace(path)
    except OSError as exc:
        version_slug = PIPELINE_VERSION.replace(".", "p")
        fallback_path = dirs["rhino"] / f"{output_base}_v{version_slug}.3dm"
        if fallback_path.exists():
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            fallback_path = dirs["rhino"] / f"{output_base}_v{version_slug}_{stamp}.3dm"
        tmp_path.replace(fallback_path)
        active_path = fallback_path
        target_replace_status = "target_locked_versioned_output"
        target_replace_error = str(exc)
    pd.DataFrame(layer_rows).to_csv(dirs["rhino"] / f"{output_base}_layers.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(object_rows).to_csv(dirs["rhino"] / f"{output_base}_object_mapping.csv", index=False, encoding="utf-8-sig")
    metadata = {
        "file": rel_project_path(active_path),
        "file_basename": active_path.stem,
        "canonical_file": rel_project_path(path),
        "canonical_file_basename": output_base,
        "target_replace_status": target_replace_status,
        "target_replace_error": target_replace_error,
        "created_at": now_iso(),
        "pipeline_version": PIPELINE_VERSION,
        "rhino_unit": "meter",
        "rhino_version": config.rhino_version,
        "voxel_size_m": config.voxel_size_m,
        "layer_count": len(layer_rows),
        "object_count": object_count,
        "road_centerline_curve_count": road_centerline_curve_count,
        "building_group_count": building_group_count,
        "building_mesh_count": building_mesh_count,
        "building_unit_voxel_box_count": building_unit_voxel_box_count,
        "rhino_unit_voxel_mesh_chunk_boxes": config.rhino_unit_voxel_mesh_chunk_boxes,
        "component_mesh_object_count": component_mesh_object_count,
        "topology_clean_mesh_object_count": topology_clean_mesh_object_count,
        "clean_mesh_wire_object_count": clean_mesh_wire_object_count,
        "rhino_component_mesh_max_runs": config.rhino_component_mesh_max_runs,
        "rhino_clean_mesh_wire_display": config.rhino_clean_mesh_wire_display,
        "building_unit_voxel_requested": config.rhino_export_mode == "building_voxel_groups",
        "building_unit_voxel_expanded": bool(expand_building_voxels),
        "component_mesh_grouped": config.rhino_export_mode == "component_mesh_groups",
        "unit_voxel_fallback_reason": unit_voxel_fallback_reason,
        "lcz_info_text_count": lcz_info_text_count,
        "geo_info_text_count": geo_info_text_count,
        "geo_info_layer": layers["geo_info"],
        "total_sparse_runs": int(len(runs)),
        "total_voxels_represented": int(runs["voxel_count"].sum()),
        "layer_voxel_counts": {k: int(v) for k, v in runs.groupby("layer")["voxel_count"].sum().to_dict().items()},
        "colors_rgba": colors,
        "export_mode": config.rhino_export_mode,
        "note": (
            f"The executed voxel grid is {config.voxel_size_m:g} m. "
            "In component_mesh_groups mode, buildings are grouped per building and exported as run-length merged voxel meshes, while terrain, roads, grass, trees, and water are exported as semantic component meshes. "
            "Building and building-base meshes use a merged run shell when possible so internal side faces are not written, and Rhino mesh wires are hidden for cleaner visual review when rhino_clean_mesh_wire_display is enabled. "
            "The Geographic_Coordinate_Info layer stores center, bbox, local-axis, and corner WGS84/elevation text dots. "
            "This preserves the configured stair-step voxel boundary without writing every unit cube as separate mesh faces. "
            "Use building_voxel_groups only when visible per-unit building boxes are needed for inspection; sparse_voxels.csv preserves the full voxel accounting in all modes."
        ),
    }
    write_json(dirs["rhino"] / f"{output_base}_metadata.json", metadata)
    return metadata


def export_gis(layers: dict[str, gpd.GeoDataFrame], local: dict[str, gpd.GeoDataFrame], config: RunConfig, dirs: dict[str, Path], dem_surface: dict[str, Any] | None = None) -> list[dict]:
    artifacts = []
    aoi_lonlat = gpd.GeoDataFrame([{"name": "aoi_boundary", "geometry": Polygon([
        lonlat_from_xy(-config.half_size_m, -config.half_size_m, config.center_lon, config.center_lat),
        lonlat_from_xy(-config.half_size_m, config.half_size_m, config.center_lon, config.center_lat),
        lonlat_from_xy(config.half_size_m, config.half_size_m, config.center_lon, config.center_lat),
        lonlat_from_xy(config.half_size_m, -config.half_size_m, config.center_lon, config.center_lat),
    ])}], crs="EPSG:4326")
    gis_map = {
        "buildings": "fused_buildings.gpkg",
        "roads": "fused_roads.gpkg",
        "water": "fused_water.gpkg",
        "green": "fused_green.gpkg",
        "poi": "fused_poi.gpkg",
    }
    for name, filename in gis_map.items():
        path = dirs["gis"] / filename
        try:
            gdf = layers[name]
            if gdf.empty:
                gdf = gpd.GeoDataFrame({"empty_reason": ["no features in AOI"]}, geometry=[Point(config.center_lon, config.center_lat)], crs="EPSG:4326")
            gdf.to_file(path, driver="GPKG", engine="pyogrio")
            artifacts.append({"artifact": filename, "status": "written", "path": rel_project_path(path)})
        except Exception as exc:
            fallback = dirs["gis"] / filename.replace(".gpkg", ".geojson")
            layers[name].to_file(fallback, driver="GeoJSON")
            artifacts.append({"artifact": filename, "status": "fallback_geojson", "path": rel_project_path(fallback), "error": str(exc)})
    aoi_path = dirs["gis"] / "aoi_boundary.gpkg"
    aoi_lonlat.to_file(aoi_path, driver="GPKG", engine="pyogrio")
    artifacts.append({"artifact": "aoi_boundary.gpkg", "status": "written", "path": rel_project_path(aoi_path)})

    xs = np.linspace(-config.half_size_m, config.half_size_m, 161)
    ys = np.linspace(-config.half_size_m, config.half_size_m, 161)
    xx, yy = np.meshgrid(xs, ys)
    zz = terrain_z(xx, yy, config, dem_surface)
    terrain_df = pd.DataFrame({"x_m": xx.ravel(), "y_m": yy.ravel(), "z_m": zz.ravel()})
    terrain_path = dirs["gis"] / "terrain_mesh.csv"
    terrain_df.to_csv(terrain_path, index=False, encoding="utf-8-sig")
    artifacts.append({"artifact": "terrain_mesh.csv", "status": "written", "path": rel_project_path(terrain_path)})
    return artifacts


def export_voxels(runs: pd.DataFrame, mapping_df: pd.DataFrame, config: RunConfig, dirs: dict[str, Path]) -> list[dict]:
    artifacts = []
    config_data = grid_config(config)
    write_json(dirs["voxels"] / "voxel_grid_config.json", config_data)
    artifacts.append({"artifact": "voxel_grid_config.json", "status": "written", "path": rel_project_path(dirs["voxels"] / "voxel_grid_config.json")})
    sparse_csv = dirs["voxels"] / "sparse_voxels.csv"
    runs.to_csv(sparse_csv, index=False, encoding="utf-8-sig")
    artifacts.append({"artifact": "sparse_voxels.csv", "status": "written", "path": rel_project_path(sparse_csv), "note": "Parquet engine unavailable; CSV is the executed sparse representation."})
    try:
        parquet = dirs["voxels"] / "sparse_voxels.parquet"
        runs.to_parquet(parquet, index=False)
        artifacts.append({"artifact": "sparse_voxels.parquet", "status": "written", "path": rel_project_path(parquet)})
    except Exception as exc:
        artifacts.append({"artifact": "sparse_voxels.parquet", "status": "skipped", "reason": f"pandas parquet engine unavailable: {exc}"})
    mapping_path = dirs["voxels"] / "voxel_element_mapping.csv"
    mapping_df.to_csv(mapping_path, index=False, encoding="utf-8-sig")
    artifacts.append({"artifact": "voxel_element_mapping.csv", "status": "written", "path": rel_project_path(mapping_path)})
    summary = runs.groupby("layer").agg(run_count=("layer", "size"), voxel_count=("voxel_count", "sum")).reset_index()
    summary["voxel_size_m"] = config.voxel_size_m
    summary["voxelization_readiness_score"] = 0.75
    summary_path = dirs["voxels"] / "voxel_quality_summary.csv"
    summary.to_csv(summary_path, index=False, encoding="utf-8-sig")
    artifacts.append({"artifact": "voxel_quality_summary.csv", "status": "written", "path": rel_project_path(summary_path)})
    return artifacts


def export_layer_element_statistics(runs: pd.DataFrame, mapping_df: pd.DataFrame, config: RunConfig, dirs: dict[str, Path]) -> None:
    layers = voxel_layer_names(config)

    def metadata_for(element_id: str) -> dict[str, Any]:
        exact = mapping_df[mapping_df["element_id"] == element_id]
        if not exact.empty:
            return exact.iloc[0].to_dict()
        for prefix, key in [("tree_canopy_", "tree_canopy_samples"), ("grass_residual_", "grass_residual")]:
            if element_id.startswith(prefix):
                matched = mapping_df[mapping_df["element_id"] == key]
                if not matched.empty:
                    return matched.iloc[0].to_dict()
        return {}

    grouped = runs.groupby(["layer", "element_id"], dropna=False).agg(
        run_count=("layer", "size"),
        voxel_count=("voxel_count", "sum"),
        x_min=("x_min", "min"),
        x_max=("x_max", "max"),
        y_min=("y_min", "min"),
        y_max=("y_max", "max"),
        z_min=("z_min", "min"),
        z_max=("z_max", "max"),
    ).reset_index()
    grouped["voxel_size_m"] = config.voxel_size_m
    grouped["represented_volume_m3"] = grouped["voxel_count"] * (config.voxel_size_m ** 3)
    grouped["plan_extent_area_m2"] = (grouped["x_max"] - grouped["x_min"]) * (grouped["y_max"] - grouped["y_min"])
    meta_rows = [metadata_for(str(row.element_id)) for row in grouped.itertuples(index=False)]
    grouped["element_type"] = [row.get("element_type", "") for row in meta_rows]
    grouped["source"] = [row.get("source", "") for row in meta_rows]
    grouped["confidence"] = [row.get("confidence", "") for row in meta_rows]
    grouped["voxelization_rule"] = [row.get("voxelization_rule", "") for row in meta_rows]

    ordered_columns = [
        "layer", "element_type", "element_id", "source", "confidence", "run_count", "voxel_count",
        "voxel_size_m", "represented_volume_m3", "plan_extent_area_m2", "x_min", "x_max", "y_min",
        "y_max", "z_min", "z_max", "voxelization_rule",
    ]
    stats_path = dirs["tables"] / "layer_element_statistics.csv"
    grouped[ordered_columns].to_csv(stats_path, index=False, encoding="utf-8-sig")

    layer_summary = grouped.groupby("layer").agg(
        element_count=("element_id", "nunique"),
        run_count=("run_count", "sum"),
        voxel_count=("voxel_count", "sum"),
        represented_volume_m3=("represented_volume_m3", "sum"),
        z_min=("z_min", "min"),
        z_max=("z_max", "max"),
    ).reset_index()
    layer_summary["voxel_size_m"] = config.voxel_size_m
    layer_summary.to_csv(dirs["tables"] / "layer_summary_statistics.csv", index=False, encoding="utf-8-sig")

    vegetation = grouped[grouped["layer"].isin([layers["trees"], layers["grass"]])].copy()
    vegetation_sources = vegetation["source"].astype(str) if not vegetation.empty else pd.Series(dtype=str)
    uses_worldcover = vegetation_sources.str.contains("ESA WorldCover", case=False, na=False).any()
    uses_osm_tree_like = vegetation_sources.str.contains("OpenStreetMap", case=False, na=False).any()
    uses_roadside_tree_layout = vegetation_sources.str.contains("road centerline-derived street tree", case=False, na=False).any()
    uses_fallback = vegetation_sources.str.contains("fallback", case=False, na=False).any()
    if uses_worldcover:
        source_note = "Current vegetation is derived from ESA WorldCover classes in the local raster crop, with retained OSM tree/tree_row features when available and optional road-centerline-derived street-tree layout. Tree canopies are sampled from source tree polygons, tree points, tree-row lines, and configured roadside spacing; grass/ground cover uses green land-cover polygons. No residual all-AOI grass fallback is used when WorldCover succeeds."
    else:
        source_note = "Current vegetation is OSM green polygons when available plus deterministic fallback grass/canopy placeholders and optional road-centerline-derived street-tree layout. It is suitable for layer completeness checks, not authoritative tree inventory."
    vegetation_summary = {
        "tree_canopy_element_count": int((vegetation["layer"] == layers["trees"]).sum()),
        "grass_ground_cover_element_count": int((vegetation["layer"] == layers["grass"]).sum()),
        "vegetation_run_count": int(vegetation["run_count"].sum()) if not vegetation.empty else 0,
        "vegetation_voxel_count": int(vegetation["voxel_count"].sum()) if not vegetation.empty else 0,
        "vegetation_represented_volume_m3": round(float(vegetation["represented_volume_m3"].sum()), 3) if not vegetation.empty else 0.0,
        "uses_osm_tree_or_tree_row": bool(uses_osm_tree_like),
        "uses_roadside_tree_layout": bool(uses_roadside_tree_layout),
        "roadside_tree_spacing_m": config.roadside_tree_spacing_m,
        "roadside_tree_offset_m": config.roadside_tree_offset_m,
        "roadside_tree_intersection_clearance_m": config.roadside_tree_intersection_clearance_m,
        "roadside_tree_merge_distance_m": config.roadside_tree_merge_distance_m,
        "source_note": source_note,
        "quality_flag": "fallback_vegetation" if uses_fallback and not uses_worldcover else "source_vegetation_enhanced",
    }
    write_json(dirs["tables"] / "vegetation_layer_quality_summary.json", vegetation_summary)


def quality_audit(layers: dict[str, gpd.GeoDataFrame], runs: pd.DataFrame, rhino_meta: dict[str, Any], config: RunConfig, dirs: dict[str, Path], dem_surface: dict[str, Any] | None = None) -> pd.DataFrame:
    feature_counts = {k: len(v) for k, v in layers.items()}
    geometry_quality = {k: 1.0 if len(v) == 0 else float(v.geometry.is_valid.mean()) for k, v in layers.items()}
    src_values = {
        "coverage_score": min(1.0, (feature_counts["buildings"] + feature_counts["roads"] + feature_counts["poi"]) / 20),
        "geometry_quality_score": float(np.mean(list(geometry_quality.values()))),
        "attribute_completeness_score": 0.70,
        "recency_score": 0.65,
        "license_reproducibility_score": 0.90,
        "china_applicability_score": 0.70,
    }
    source_selection = source_score(src_values)
    height_values = {
        "height_source_reliability": 0.55,
        "cross_source_consistency": 0.45,
        "local_context_plausibility": 0.70,
        "geometry_validity_score": geometry_quality.get("buildings", 1.0),
    }
    height_conf = weighted_score("height_confidence_score", height_values)
    readiness_values = {
        "geometry_validity_score": float(np.mean(list(geometry_quality.values()))),
        "height_confidence_score": height_conf,
        "crs_confidence_score": 0.90,
        "source_selection_score": source_selection,
        "topology_cleanliness_score": 0.80,
    }
    readiness = weighted_score("voxelization_readiness_score", readiness_values)
    final_values = {
        "building_coverage_quality": min(1.0, feature_counts["buildings"] / 5) if feature_counts["buildings"] else 0.35,
        "height_attribute_quality": height_conf,
        "road_network_quality": min(1.0, feature_counts["roads"] / 4) if feature_counts["roads"] else 0.30,
        "terrain_quality": 0.75 if dem_surface and dem_surface.get("metadata", {}).get("status") == "success" else 0.45,
        "green_water_semantic_quality": min(1.0, (feature_counts["green"] + feature_counts["water"] + 1) / 4),
        "crs_and_alignment_quality": 0.90,
        "voxelization_completeness": 0.95 if rhino_meta["total_voxels_represented"] > 0 else 0.0,
    }
    final_score = weighted_score("final_model_quality_score", final_values)

    def layer_source(element: str) -> str:
        if element == "terrain":
            metadata = (dem_surface or {}).get("metadata", {})
            return str(metadata.get("source", "procedural DEM fallback"))
        if element == "voxel":
            return "Generated from fused layer geometries, DEM terrain, and voxel_element_mapping.csv"
        if element == "rhino":
            return "Generated from sparse voxel runs with Rhino layer colors preserved"
        gdf = layers.get(element)
        if gdf is not None and not gdf.empty and "source" in gdf.columns:
            values = [
                str(value)
                for value in pd.Series(gdf["source"]).dropna().unique().tolist()
                if str(value).strip()
            ]
            if values:
                return "; ".join(sorted(values)[:5])
        return "No source features in current AOI"

    def source_confidence(element: str) -> str:
        if element == "terrain":
            return "high" if is_real_dem(dem_surface) else "low"
        if element in ("voxel", "rhino"):
            return "medium-to-high" if rhino_meta["total_voxels_represented"] > 0 else "low"
        return "medium" if feature_counts.get(element, 0) > 0 else "low"

    rows = []
    for element in ["buildings", "roads", "water", "green", "poi", "terrain", "voxel", "rhino"]:
        rows.append({
            "element": element,
            "feature_count": feature_counts.get(element, 1 if element in ("terrain", "voxel", "rhino") else 0),
            "source_selection_score": source_selection,
            "geometry_quality_deviation_score": round(1 - geometry_quality.get(element, 0.85), 4),
            "source_conflict_score": 0.0,
            "height_confidence_score": height_conf if element in ("buildings", "voxel", "rhino") else "",
            "voxelization_readiness_score": readiness,
            "final_model_quality_score": final_score,
            "source": layer_source(element),
            "confidence": source_confidence(element),
            "resolution": f"{config.voxel_size_m} m output voxel grid; source precision varies",
            "timestamp": now_iso(),
            "license": "ODbL-1.0 for OSM-derived layers; generated outputs CC-BY-compatible subject to source attribution",
            "processing_step": "fusion->voxelization->rhino_export",
            "geometry_validity": geometry_quality.get(element, 1.0),
            "voxelization_rule": "see voxel_element_mapping.csv",
        })
    df = pd.DataFrame(rows)
    df.to_csv(dirs["audit"] / "data_quality_audit.csv", index=False, encoding="utf-8-sig")
    write_json(dirs["audit"] / "data_quality_audit.json", rows)
    write_json(dirs["audit"] / "score_weights.json", SCORE_WEIGHTS)
    return df


def export_basic_statistics(
    layers: dict[str, gpd.GeoDataFrame],
    local: dict[str, gpd.GeoDataFrame],
    runs: pd.DataFrame,
    rhino_meta: dict[str, Any],
    config: RunConfig,
    dirs: dict[str, Path],
    dem_surface: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def safe_area(gdf: gpd.GeoDataFrame) -> float:
        if gdf.empty:
            return 0.0
        return float(gdf.geometry.area.sum())

    def safe_length(gdf: gpd.GeoDataFrame) -> float:
        if gdf.empty:
            return 0.0
        return float(gdf.geometry.length.sum())

    morphology = compute_scene_morphology_indicators(local, config, dem_surface)
    building_heights = pd.to_numeric(layers["buildings"].get("height_m", pd.Series(dtype=float)), errors="coerce")
    road_area = float(morphology.get("road_surface_area_m2") or 0.0)
    dem_meta = (dem_surface or {}).get("metadata", {})
    layer_voxels = {k: int(v) for k, v in runs.groupby("layer")["voxel_count"].sum().to_dict().items()}
    stats = {
        "site": {
            "pipeline_version": PIPELINE_VERSION,
            "site_name": config.site_name,
            "site_name_cn": config.site_name_cn,
            "center_lat": config.center_lat,
            "center_lon": config.center_lon,
            "aoi_width_m": config.half_size_m * 2,
            "aoi_height_m": config.half_size_m * 2,
            "aoi_area_m2": (config.half_size_m * 2) ** 2,
            "voxel_size_m": config.voxel_size_m,
        },
        "features": {
            "building_count": int(len(layers["buildings"])),
            "road_count": int(len(layers["roads"])),
            "water_count": int(len(layers["water"])),
            "green_count": int(len(layers["green"])),
            "poi_count": int(len(layers["poi"])),
            "building_footprint_area_m2": morphology.get("building_footprint_area_m2"),
            "building_height_min_m": None if building_heights.dropna().empty else round(float(building_heights.min()), 3),
            "building_height_mean_m": None if building_heights.dropna().empty else round(float(building_heights.mean()), 3),
            "building_height_max_m": None if building_heights.dropna().empty else round(float(building_heights.max()), 3),
            "road_centerline_length_m": round(safe_length(local["roads"]), 3),
            "road_surface_area_m2": round(road_area, 3),
            "green_polygon_area_m2": round(safe_area(local["green"]), 3),
            "water_polygon_area_m2": round(safe_area(local["water"]), 3),
        },
        "morphology": morphology,
        "formulas": MORPHOLOGY_FORMULAS,
        "dem": {
            "source": dem_meta.get("source"),
            "status": dem_meta.get("status"),
            "tile_zoom": dem_meta.get("tile_zoom"),
            "grid_spacing_m": dem_meta.get("grid_spacing_m"),
            "min_elevation_m": dem_meta.get("min_elevation_m"),
            "mean_elevation_m": dem_meta.get("mean_elevation_m"),
            "max_elevation_m": dem_meta.get("max_elevation_m"),
            "elevation_range_m": dem_meta.get("elevation_range_m"),
        },
        "voxels": {
            "sparse_run_count": int(len(runs)),
            "total_voxels_represented": int(runs["voxel_count"].sum()),
            "layer_voxel_counts": layer_voxels,
        },
        "rhino": {
            "object_count": rhino_meta.get("object_count"),
            "layer_count": rhino_meta.get("layer_count"),
            "file": rhino_meta.get("file"),
        },
    }
    rows = []
    for category, values in stats.items():
        if isinstance(values, dict):
            for key, value in values.items():
                if isinstance(value, dict):
                    for subkey, subvalue in value.items():
                        rows.append({"category": category, "metric": f"{key}.{subkey}", "value": subvalue})
                else:
                    rows.append({"category": category, "metric": key, "value": value})
    stats_csv = dirs["tables"] / "basic_site_statistics.csv"
    pd.DataFrame(rows).to_csv(stats_csv, index=False, encoding="utf-8-sig")
    write_json(dirs["tables"] / "basic_site_statistics.json", stats)
    return stats


def validate_real_data_sources(
    config: RunConfig,
    dem_surface: dict[str, Any],
    layers: dict[str, gpd.GeoDataFrame],
    worldcover_landcover: dict[str, Any],
    fetch_audit: list[dict],
    dirs: dict[str, Path],
) -> dict[str, Any]:
    dem_meta = dem_surface.get("metadata", {})
    worldcover_meta = worldcover_landcover.get("metadata", {})
    osm_audit = fetch_audit[0] if fetch_audit else {}
    checks = {
        "strict_real_data": bool(config.strict_real_data),
        "dem_status": dem_meta.get("status"),
        "worldcover_status": worldcover_meta.get("status"),
        "osm_provider": osm_audit.get("provider"),
        "building_count": int(len(layers.get("buildings", []))),
        "road_count": int(len(layers.get("roads", []))),
        "worldcover_selection_status": worldcover_meta.get("raster_selection", {}).get("selection_status"),
        "worldcover_expected_tiles": worldcover_meta.get("expected_tiles") or worldcover_meta.get("raster_selection", {}).get("expected_tiles"),
        "uses_dem_fallback": dem_meta.get("status") != "success",
        "uses_worldcover_fallback": worldcover_meta.get("status") != "success",
        "uses_osm_empty_fallback": osm_audit.get("provider") == "fallback_empty",
    }
    failures: list[str] = []
    if checks["uses_dem_fallback"]:
        failures.append("DEM is not a real successful source.")
    if checks["uses_worldcover_fallback"]:
        expected_tiles = checks.get("worldcover_expected_tiles") or []
        suffix = f" Expected local tile(s): {expected_tiles}." if expected_tiles else ""
        failures.append("ESA WorldCover land-cover raster is not successfully loaded." + suffix)
    if checks["uses_osm_empty_fallback"]:
        failures.append("OSM Overpass returned fallback_empty.")
    result = {
        "timestamp": now_iso(),
        "mode": "strict" if config.strict_real_data else "audit_only",
        "status": "failed" if failures and config.strict_real_data else "passed_with_warnings" if failures else "passed",
        "checks": checks,
        "failures": failures,
        "note": "Strict mode fails before formal output if any core source falls back to synthetic or empty data. Feature-count expectations are enforced by site QA thresholds.",
    }
    write_json(dirs["audit"] / "real_data_source_check.json", result)
    if config.strict_real_data and failures:
        raise RuntimeError("Strict real-data check failed: " + "; ".join(failures))
    return result


def classify_scene_alcc_lcz(
    stats: dict[str, Any],
    runs: pd.DataFrame,
    config: RunConfig,
    dirs: dict[str, Path],
) -> dict[str, Any]:
    site = stats.get("site", {})
    features = stats.get("features", {})
    dem = stats.get("dem", {})
    morphology = dict(stats.get("morphology") or {})
    if not morphology:
        aoi_area = float(site.get("aoi_area_m2") or (config.half_size_m * 2) ** 2)
        building_area = float(features.get("building_footprint_area_m2") or 0.0)
        road_area = float(features.get("road_surface_area_m2") or 0.0)
        green_area = float(features.get("green_polygon_area_m2") or 0.0)
        water_area = float(features.get("water_polygon_area_m2") or 0.0)
        road_length = float(features.get("road_centerline_length_m") or 0.0)
        morphology = {
            "aoi_area_m2": round(aoi_area, 3),
            "building_footprint_area_m2": round(building_area, 3),
            "building_coverage_ratio": round(building_area / aoi_area if aoi_area else 0.0, 4),
            "road_surface_area_m2": round(road_area, 3),
            "green_area_m2": round(green_area, 3),
            "water_area_m2": round(water_area, 3),
            "green_ratio": round(green_area / aoi_area if aoi_area else 0.0, 4),
            "water_ratio": round(water_area / aoi_area if aoi_area else 0.0, 4),
            "impervious_surface_ratio": round(min(1.0, (building_area + road_area) / aoi_area), 4) if aoi_area else 0.0,
            "building_height_mean_m": round(float(features.get("building_height_mean_m") or 0.0), 3),
            "building_height_max_m": round(float(features.get("building_height_max_m") or 0.0), 3),
            "road_density_km_per_km2": round((road_length / 1000.0) / (aoi_area / 1_000_000.0), 3) if aoi_area else 0.0,
            "terrain_relief_m": round(float(dem.get("elevation_range_m") or 0.0), 3),
            "open_space_ratio": round(1.0 - building_area / aoi_area, 4) if aoi_area else 0.0,
        }
    classification = classify_scene_from_morphology(morphology)
    metrics = {
        **morphology,
        "building_surface_fraction": morphology.get("building_coverage_ratio"),
        "impervious_surface_fraction_proxy": morphology.get("impervious_surface_ratio"),
        "green_surface_fraction": morphology.get("green_ratio"),
        "water_surface_fraction": morphology.get("water_ratio"),
        "mean_building_height_m": morphology.get("building_height_mean_m"),
        "max_building_height_m": morphology.get("building_height_max_m"),
        "total_sparse_runs": int(len(runs)),
        "total_voxels_represented": int(runs["voxel_count"].sum()) if not runs.empty else 0,
    }
    result = {
        "timestamp": now_iso(),
        "pipeline_version": PIPELINE_VERSION,
        "site_name": config.site_name,
        "site_name_cn": config.site_name_cn,
        "center": {"lat": config.center_lat, "lon": config.center_lon},
        "classification": classification,
        "metrics": metrics,
        "formulas": MORPHOLOGY_FORMULAS,
        "threshold_note": "LCZ thresholds are simplified for research QA and should be calibrated against official LCZ training samples before publication claims.",
    }
    write_json(dirs["tables"] / "scene_classification_alcc_lcz.json", result)
    pd.DataFrame([metrics]).to_csv(dirs["tables"] / "scene_classification_metrics.csv", index=False, encoding="utf-8-sig")
    notes = [
        "# Scene Morphology And LCZ Formula Notes",
        "",
        f"Pipeline version: v{PIPELINE_VERSION}",
        "",
        "This scene-level LCZ is a transparent rule-based design-screening estimate. The 250 m grid LCZ workflow remains in `src/urban_morphology`.",
        "",
        "## Formulas",
        "",
    ]
    for key, formula in MORPHOLOGY_FORMULAS.items():
        notes.append(f"- `{key}`: `{formula}`")
    notes.extend([
        "",
        "## Limitation",
        "",
        "`sky_view_factor_proxy` is a morphology proxy, not a hemispherical ray-traced SVF. Use it for screening only.",
        "",
    ])
    (dirs["tables"] / "scene_morphology_lcz_formula_notes.md").write_text("\n".join(notes), encoding="utf-8")
    return result


def make_figures(layers: dict[str, gpd.GeoDataFrame], local: dict[str, gpd.GeoDataFrame], runs: pd.DataFrame, audit: pd.DataFrame, dirs: dict[str, Path], config: RunConfig) -> None:
    fig_dir = dirs["figures"]
    colors_by_layer = layer_color_map(config)
    # Study area overview.
    fig, ax = plt.subplots(figsize=(7, 7), dpi=180)
    ax.set_title("Study Area and Fused OSM Layers")
    ax.set_aspect("equal")
    ax.add_patch(plt.Rectangle((-config.half_size_m, -config.half_size_m), 2 * config.half_size_m, 2 * config.half_size_m, fill=False, color="black", linewidth=1.5))
    for name, color in [("green", "#88b053"), ("water", "#419bdf"), ("roads", "#333333"), ("buildings", "#c4281b")]:
        gdf = local[name]
        if not gdf.empty:
            gdf.plot(ax=ax, color=color, linewidth=0.8, alpha=0.70)
    ax.set_xlabel("local x (m)")
    ax.set_ylabel("local y (m)")
    fig.tight_layout()
    fig.savefig(fig_dir / "study_area_data_sources.png")
    plt.close(fig)

    for fname, title, lines in [
        ("data_fusion_workflow.png", "Data Fusion Workflow", ["Input AOI", "Source registry", "OSM/local/fallback fetch", "CRS normalization", "Conflict audit", "Fused GIS layers"]),
        ("voxelization_workflow.png", f"{config.voxel_size_m:g} m Sparse Voxelization Workflow", ["AOI estimate", "Sparse masks", "Run-length cuboids", "Layer mapping", "Rhino 3DM", "Audit package"]),
    ]:
        fig, ax = plt.subplots(figsize=(9, 2.8), dpi=180)
        ax.axis("off")
        for i, text in enumerate(lines):
            x = 0.08 + i * 0.155
            ax.text(x, 0.55, text, ha="center", va="center", bbox=dict(boxstyle="round,pad=0.25", fc="#f2f2f2", ec="#444"), fontsize=8)
            if i < len(lines) - 1:
                ax.annotate("", xy=(x + 0.07, 0.55), xytext=(x + 0.11, 0.55), arrowprops=dict(arrowstyle="<-", color="#444"))
        ax.set_title(title)
        fig.tight_layout()
        fig.savefig(fig_dir / fname)
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4), dpi=180)
    layer_counts = runs.groupby("layer")["voxel_count"].sum().sort_values()
    layer_counts.plot(kind="barh", ax=ax, color="#53777a")
    ax.set_title(f"Rhino Layer Preview: represented {config.voxel_size_m:g} m voxel counts")
    ax.set_xlabel("voxel count")
    fig.tight_layout()
    fig.savefig(fig_dir / "rhino_layer_preview.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 4), dpi=180)
    audit.set_index("element")["final_model_quality_score"].astype(float).plot(kind="bar", ax=ax, color="#8fb339")
    ax.set_ylim(0, 1)
    ax.set_title("Element Quality Summary")
    fig.tight_layout()
    fig.savefig(fig_dir / "element_quality_summary.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 7), dpi=180)
    ax.set_aspect("equal")
    for layer, group in runs.groupby("layer"):
        color = np.array(colors_by_layer.get(layer, (120, 120, 120, 255))[:3]) / 255
        sample = group.sample(min(len(group), 3000), random_state=1)
        ax.scatter((sample["x_min"] + sample["x_max"]) / 2, (sample["y_min"] + sample["y_max"]) / 2, s=0.3, color=color, alpha=0.5)
    ax.set_title("Final Model Overview (sampled sparse voxel runs)")
    ax.set_xlabel("local x (m)")
    ax.set_ylabel("local y (m)")
    fig.tight_layout()
    fig.savefig(fig_dir / "final_model_overview.png")
    plt.close(fig)


def write_docs(config: RunConfig, artifacts: list[dict], audit: pd.DataFrame, rhino_meta: dict[str, Any], dirs: dict[str, Path], run_report: dict[str, Any], dem_surface: dict[str, Any] | None = None) -> None:
    docs = dirs["docs"]
    output_base = rhino_output_base(config)
    artifact_df = pd.DataFrame(artifacts)
    artifact_df.to_csv(dirs["tables"] / "artifact_mapping.csv", index=False, encoding="utf-8-sig")
    artifact_md_table = dataframe_to_markdown(artifact_df.fillna("").astype(str))
    artifact_md = ["# Artifact Mapping\n", "All listed files are generated by the executed notebook pipeline.\n", artifact_md_table]
    (docs / "artifact_mapping.md").write_text("\n\n".join(artifact_md), encoding="utf-8")

    provenance = {
        "created_at": now_iso(),
        "project_root": str(PROJECT_ROOT),
        "config": asdict(config),
        "source_registry": rel_project_path(dirs["tables"] / "data_source_registry.json"),
        "coordinate_transform": {
            "source_crs": "EPSG:4326 WGS84",
            "target_crs": "local tangent-plane meter coordinate system",
            "transform_method": "equirectangular local projection centered at AOI centroid",
            "max_expected_error": "sub-meter for this micro AOI; not a national-scale CRS replacement",
            "code_function": "local_xy / lonlat_from_xy",
            "timestamp": now_iso(),
        },
        "rhino_origin": "AOI centroid; x east, y north, z meters above the selected DEM/local terrain datum",
        "dem_surface": (dem_surface or {}).get("metadata", {}),
    }
    write_json(docs / "provenance.json", provenance)
    (docs / "provenance.md").write_text(
        "# Provenance\n\n"
        f"本次流程由 notebook 重新执行生成，项目根目录为 `{PROJECT_ROOT}`。输入中心点为 `{config.center_lat}, {config.center_lon}`，"
        f"AOI 半宽为 `{config.half_size_m} m`，目标输出体素分辨率为 `{config.voxel_size_m} m`。所有 OSM 原始响应缓存位于 `01_raw`，"
        "地形在未提供本地 DEM 时使用程序化低置信度曲面，并在 audit 中标注。\n\n"
        "坐标转换采用 WGS84 到 AOI 质心局部米制坐标的等距近似，Rhino 单位为 meter。若后续接入天地图、高德或百度数据，必须先记录其返回坐标系并执行 WGS84/GCJ-02/BD-09 可审计转换。\n",
        encoding="utf-8",
    )
    env_lines = [
        "# Environment Report",
        f"- Python: `{sys.version}`",
        f"- Platform: `{platform.platform()}`",
        f"- Working directory: `{PROJECT_ROOT}`",
        f"- Generated at: `{now_iso()}`",
        f"- Rhino writer: `rhino3dm`",
        f"- Notebook runner: project-local JSON runner because nbconvert/nbformat are not installed.",
    ]
    (docs / "environment_report.md").write_text("\n".join(env_lines), encoding="utf-8")

    summary = [
        "# Paper-ready Summary",
        f"本次执行生成了面向中国城市建成环境的 `{config.voxel_size_m:g} m` 稀疏体素 Rhino 模型。AOI 为 `{config.site_name_cn}`，中心点 `{config.center_lat}, {config.center_lon}`，半宽 `{config.half_size_m} m`。",
        f"Rhino 输出为 `05_rhino/{output_base}.3dm`，Rhino 对象数 `{rhino_meta['object_count']}`，表示的 `{config.voxel_size_m:g} m` 体素数 `{rhino_meta['total_voxels_represented']}`。",
        "核心评分见 `07_audit/data_quality_audit.csv`；数据源、许可、坐标转换和 fallback 记录见 `11_docs/provenance.md` 与 `06_tables/data_source_registry.csv`。",
    ]
    (docs / "paper_ready_summary.md").write_text("\n\n".join(summary), encoding="utf-8")

    detailed = f"""# 完整流程详细介绍

本文件由项目本地 pipeline 重新执行生成，服务于论文写作、答辩汇报、团队交接和代码复现。流程目标是把给定的中国境内坐标点或 AOI 转换为可审计的多源城市空间数据包，并进一步生成 Rhino 可读的 `{config.voxel_size_m:g} m` 稀疏体素模型。这里的 `{config.voxel_size_m:g} m` 表示输出几何体素化网格分辨率，不表示所有源数据都具有同等真实测量精度；源数据精度、许可、时间戳和推断方法均在 provenance 与 audit 文件中记录。

## 研究目标、输入与 AOI 判断

本次默认案例为 `{config.site_name_cn}`，中心 WGS84 坐标为 `{config.center_lat}, {config.center_lon}`，AOI 为中心点向四周 `{config.half_size_m}` 米的局部正方形。程序首先计算 `voxel_grid_config.json`，其中明确写入 `voxel_size_m = {config.voxel_size_m}`、`nx`、`ny`、`nz`、dense 等价体素数量、预估内存、预估文件规模和是否需要 tiled/chunked 模式。若 AOI 增大到 dense 等价体素超过阈值，程序不会静默降分辨率，而是标记 tiled/chunked 输出；只有用户设置 `allow_resolution_fallback=true` 时，才允许生成较低分辨率预览模型。

## 中国数据源注册与排序

数据源优先级由 `src/data_source_registry.py` 显式注册，输出为 `06_tables/data_source_registry.csv/json`。建筑 footprint 的优先级为本地高质量矢量、Overture Maps、OSM/Geofabrik、Microsoft 或其他开放 footprint、遥感推断；建筑高度优先本地权威高度、开放 LoD/高度数据、DSM-DEM 差值、楼层字段乘以可配置层高、建筑类型推断。道路、水体、绿地、POI 和地形也采用同样的注册与 fallback 机制。没有 API key 或许可不确定的数据源，例如天地图、高德或百度 API，在本次默认流程中不会参与几何主输出，只在注册表中记录其潜在用途和启用条件。

## 数据融合、坐标转换与 Rhino 局部坐标原点

所有在线 OSM 数据以 WGS84 读取，并按站点名称缓存为 `01_raw/osm_overpass_combined_raw_<site_name>.json`；旧的通用缓存仅作为 legacy 原始记录保留，不参与当前运行。进入几何融合前，程序将经纬度转换到以 AOI 质心为原点的局部米制坐标系，x 轴指向东、y 轴指向北、z 轴单位为米。转换函数为 `local_xy` 与 `lonlat_from_xy`，记录于 `11_docs/provenance.md/json` 和 `origin_mapping.json`。该局部投影适用于本次微 AOI；若扩展到城市级或省级范围，应替换为 CGCS2000/UTM 等正式投影，并在 transformation pipeline 中记录 EPSG、误差和代码函数。

## 建筑、道路、水体、绿地、地形与 POI 处理

建筑来自 OSM building way。若存在 height 字段则直接使用；若存在 building:levels 则按默认 3.3 m 层高推断；若均缺失，则按建筑类型给出 estimated height，并降低 height_confidence_score。道路由 highway centerline 根据等级或 width 字段估计宽度，缓冲为硬质铺装面后进行 `{config.voxel_size_m:g} m` 表面体素化。水体使用 natural=water、waterway 等标签。绿地优先使用 OSM leisure、landuse、natural 植被相关面；若 AOI 内绿地不足，剩余裸露地表会作为低置信度 grass/ground cover fallback。地形在没有本地 DEM 时使用程序化曲面，目的只是为 Rhino 与风环境前处理提供可复现的 z 基准，不能作为实测 DEM 解释。POI 以 amenity、shop、tourism、public_transport 等节点作为语义标注，不一定参与主几何体素化。

## 体素化定义与分块策略

体素化采用稀疏 run-length 表示。建筑 footprint 被栅格化为 `{config.voxel_size_m:g} m` 平面单元，并从局部地形高度挤出到建筑高度；道路、水体和草地为一层表面体素；树冠为小体量语义占位体素；地形为一层 DEM surface voxel。Rhino 中并不逐个写入每个小立方体，而是将连续体素合并成 cuboid mesh chunk，同时在 `04_voxels/sparse_voxels.csv`、`04_voxels/voxel_element_mapping.csv` 和 `05_rhino/{output_base}_object_mapping.csv` 中保存体素数量与映射关系。这一策略使 Rhino 可打开，同时保持输出网格语义与审计可追溯性。

## Rhino 分层与 paper-ready 图表

Rhino 文件 `05_rhino/{output_base}.3dm` 使用 meter 单位，包含 AOI、建筑、道路硬质铺装、水体、树木、草地、地形和 POI 语义图层。图层颜色按语义角色固定，并输出到 `{output_base}_layers.csv`。paper-ready 图表位于 `10_figures`，包括研究区数据源、数据融合流程、体素化流程、Rhino 图层体素数量预览、元素质量评分和最终模型概览。

## 评分公式与 audit 指标

程序显式实现如下评分公式，并把真实权重写入 `07_audit/score_weights.json`：

`source_selection_score = 0.35 * coverage_score + 0.25 * geometry_quality_score + 0.15 * attribute_completeness_score + 0.10 * recency_score + 0.10 * license_reproducibility_score + 0.05 * china_applicability_score`

`height_confidence_score = 0.40 * height_source_reliability + 0.25 * cross_source_consistency + 0.20 * local_context_plausibility + 0.15 * geometry_validity_score`

`voxelization_readiness_score = 0.30 * geometry_validity_score + 0.25 * height_confidence_score + 0.20 * crs_confidence_score + 0.15 * source_selection_score + 0.10 * topology_cleanliness_score`

`final_model_quality_score = 0.25 * building_coverage_quality + 0.20 * height_attribute_quality + 0.15 * road_network_quality + 0.10 * terrain_quality + 0.10 * green_water_semantic_quality + 0.10 * crs_and_alignment_quality + 0.10 * voxelization_completeness`

同时输出 `source_selection_score`、`geometry_quality_deviation_score`、`source_conflict_score`、`height_confidence_score`、`voxelization_readiness_score` 和 `final_model_quality_score`，覆盖建筑、道路、水体、绿地、地形、POI、体素和 Rhino 输出。

## artifact_mapping、provenance、fallback 与旧文件清理

`artifact_mapping.md/csv` 用于把每个最终文件映射到生成阶段、路径和状态；`provenance.md/json` 记录输入、坐标转换、数据源、许可、时间戳和 Rhino 原点；`data_quality_audit.csv/json` 记录每类元素的质量指标。当前目录在执行前只有 `voxcity_demo (4).py`，未清理该原始 demo，因为它是本次优化的输入依据。流程不会在指定目录外创建、移动或删除文件。若外部数据源失败，程序使用缓存或确定性 fallback，并在 audit 中记录原因。

## 相比旧版本的提升、论文类型与后续 LBM 接口

旧 demo 依赖 Colab 授权、交互式可视化和空 Rhino 文件写出，且存在为了避免 OOM 自动降分辨率或截断体素的风险。本版本把最终入口统一到 notebook/runner，新增数据源注册、坐标审计、可配置稀疏体素分辨率、Rhino 分层映射、质量评分、provenance、artifact mapping 和 paper-ready 图表。它可支撑软件论文、方法论文或城市风环境数据前处理论文。后续接入 LBM 时，可从 `sparse_voxels.csv` 或 Rhino 图层导出 obstacle/terrain/roughness mask；后续接入街景立面雕刻或 3DGS 时，可把 facade carving 结果作为新的高优先级局部建筑表面数据源写入同一 registry 和 voxel mapping。

## 当前局限性

本地未提供权威 DEM、DSM、建筑高度或树木清查数据，因此地形、树冠和部分建筑高度仍包含低置信度推断。由于环境缺少 pyarrow/fastparquet，`sparse_voxels.parquet` 在本机执行中被跳过，使用 `sparse_voxels.csv` 作为等价稀疏体素表，并在 artifact mapping 中记录原因。若用于正式投稿，应补充本地权威数据或省级开放数据，并用相同 notebook 重新执行生成最终版。
"""
    (docs / "完整流程详细介绍.md").write_text(detailed, encoding="utf-8")
    write_json(dirs["logs"] / "run_report.json", run_report)


def dataframe_to_markdown(df: pd.DataFrame) -> str:
    if df.empty:
        return "_No rows._"
    columns = list(df.columns)
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join(["---"] * len(columns)) + " |",
    ]
    for _, row in df.iterrows():
        values = [str(row[col]).replace("|", "\\|").replace("\n", " ") for col in columns]
        lines.append("| " + " | ".join(values) + " |")
    return "\n".join(lines)


def write_origin_mapping(config: RunConfig, dirs: dict[str, Path], dem_surface: dict[str, Any] | None = None) -> None:
    origin = {
        "origin_lon": config.center_lon,
        "origin_lat": config.center_lat,
        "origin_elevation": float(terrain_z(0, 0, config, dem_surface)),
        "projected_crs": "local tangent-plane meters around WGS84 AOI centroid",
        "local_x_axis": "east",
        "local_y_axis": "north",
        "vertical_datum": (dem_surface or {}).get("metadata", {}).get("source", "procedural local terrain datum"),
        "unit": "meter",
        "transformation_pipeline": ["source WGS84 lon/lat", "local_xy equirectangular approximation", "Rhino meter coordinates"],
    }
    write_json(dirs["gis"] / "origin_mapping.json", origin)


def run_pipeline(config: RunConfig | None = None) -> dict[str, Any]:
    config = config or RunConfig()
    os.chdir(PROJECT_ROOT)
    dirs = ensure_dirs(config)
    status_path = dirs["logs"] / "stage_status.json"
    run_report: dict[str, Any] = {"started_at": now_iso(), "config": asdict(config), "stages": []}

    def stage(name: str, fn):
        start = time.perf_counter()
        try:
            result = fn()
            entry = {"stage": name, "status": "success", "seconds": round(time.perf_counter() - start, 3), "timestamp": now_iso()}
            run_report["stages"].append(entry)
            write_json(status_path, run_report)
            return result
        except Exception as exc:
            entry = {"stage": name, "status": "failed", "seconds": round(time.perf_counter() - start, 3), "error": str(exc), "traceback": traceback.format_exc(), "timestamp": now_iso()}
            run_report["stages"].append(entry)
            write_json(status_path, run_report)
            raise

    stage("export_data_source_registry", lambda: export_registry(dirs["tables"]))
    dem_surface = stage("fetch_dem_surface", lambda: fetch_dem_surface(config, dirs))
    write_origin_mapping(config, dirs, dem_surface)
    write_json(dirs["voxels"] / "voxel_grid_config.json", grid_config(config))
    layers, fetch_audit = stage("fetch_osm_layers", lambda: fetch_osm_layers(config, dirs))
    worldcover_landcover = stage("load_esa_worldcover_landcover", lambda: load_esa_worldcover_landcover(config, dirs))
    real_data_check = stage("validate_real_data_sources", lambda: validate_real_data_sources(config, dem_surface, layers, worldcover_landcover, fetch_audit, dirs))
    layers = stage("fuse_worldcover_landcover", lambda: fuse_worldcover_landcover(layers, worldcover_landcover, dirs))
    local = stage("normalize_to_local_crs", lambda: {k: to_local_gdf(v, config) for k, v in layers.items()})
    gis_artifacts = stage("export_gis_layers", lambda: export_gis(layers, local, config, dirs, dem_surface))
    runs, mapping_df = stage(f"sparse_voxelization_{voxel_size_slug(config.voxel_size_m)}", lambda: build_sparse_runs(local, config, dem_surface))
    voxel_artifacts = stage("export_voxel_tables", lambda: export_voxels(runs, mapping_df, config, dirs))
    stage("export_layer_element_statistics", lambda: export_layer_element_statistics(runs, mapping_df, config, dirs))
    rhino_meta = stage("export_rhino_3dm", lambda: export_rhino(runs, mapping_df, config, dirs, local, dem_surface))
    audit_df = stage("quality_audit", lambda: quality_audit(layers, runs, rhino_meta, config, dirs, dem_surface))
    basic_stats = stage("export_basic_site_statistics", lambda: export_basic_statistics(layers, local, runs, rhino_meta, config, dirs, dem_surface))
    scene_classification = stage("scene_classification_alcc_lcz", lambda: classify_scene_alcc_lcz(basic_stats, runs, config, dirs))
    stage("make_paper_ready_figures", lambda: make_figures(layers, local, runs, audit_df, dirs, config))

    artifacts = []
    for d in [dirs["gis"], dirs["voxels"], dirs["rhino"], dirs["tables"], dirs["audit"], dirs["figures"], dirs["docs"], dirs["logs"]]:
        for p in d.rglob("*"):
            if p.is_file():
                artifacts.append({"artifact": p.name, "path": rel_project_path(p), "bytes": p.stat().st_size, "status": "written"})
    artifacts.extend(gis_artifacts)
    artifacts.extend(voxel_artifacts)
    artifacts.append({"artifact": "fetch_audit", "status": "recorded", "details": fetch_audit})
    run_report["finished_at"] = now_iso()
    run_report["rhino_meta"] = rhino_meta
    run_report["dem_surface"] = dem_surface.get("metadata", {})
    run_report["basic_site_statistics"] = basic_stats
    run_report["real_data_source_check"] = real_data_check
    run_report["scene_classification"] = scene_classification
    run_report["artifact_count"] = len(artifacts)
    stage("write_docs", lambda: write_docs(config, artifacts, audit_df, rhino_meta, dirs, run_report, dem_surface))
    write_json(dirs["logs"] / "final_execution_report.json", run_report)
    return run_report


if __name__ == "__main__":
    report = run_pipeline()
    print(json.dumps({
        "status": "success",
        "finished_at": report.get("finished_at"),
        "rhino": report.get("rhino_meta", {}).get("file"),
        "scene_classification": report.get("scene_classification", {}).get("classification", {}),
        "artifact_count": report.get("artifact_count"),
    }, ensure_ascii=False, indent=2))
