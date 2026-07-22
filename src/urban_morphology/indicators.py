from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import LineString, MultiLineString, MultiPolygon, Polygon

from .coordinates import geometry_to_local, read_origin
from .grid import load_grid_local, prepare_grid
from .paths import MorphologyPaths, ensure_output_dirs


def _read_layer(path: Path, origin, expected: str) -> gpd.GeoDataFrame:
    if not path.exists():
        return gpd.GeoDataFrame({"missing_reason": [f"{expected} file not found"]}, geometry=[Polygon()])
    gdf = gpd.read_file(path)
    if gdf.empty:
        return gdf
    if gdf.crs is not None and gdf.crs.to_epsg() == 4326:
        geoms = [geometry_to_local(geom, origin) if geom is not None and not geom.is_empty else geom for geom in gdf.geometry]
        return gpd.GeoDataFrame(gdf.drop(columns="geometry"), geometry=geoms)
    return gdf


def _valid_geoms(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    if gdf.empty:
        return gdf
    return gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()


def _area_intersection(gdf: gpd.GeoDataFrame, cell) -> float:
    total = 0.0
    for geom in _valid_geoms(gdf).geometry:
        inter = geom.intersection(cell)
        if not inter.is_empty:
            total += inter.area
    return float(total)


def _line_length_intersection(gdf: gpd.GeoDataFrame, cell) -> float:
    total = 0.0
    for geom in _valid_geoms(gdf).geometry:
        inter = geom.intersection(cell)
        if not inter.is_empty:
            total += inter.length
    return float(total)


def _building_rows_in_cell(buildings: gpd.GeoDataFrame, cell) -> list[tuple[Any, float]]:
    rows = []
    for idx, row in _valid_geoms(buildings).iterrows():
        inter = row.geometry.intersection(cell)
        if not inter.is_empty and inter.area > 0:
            rows.append((row, float(inter.area)))
    return rows


def _polygon_orientation_weighted_length(geom) -> list[tuple[float, float]]:
    parts = list(geom.geoms) if isinstance(geom, MultiPolygon) else [geom]
    edges: list[tuple[float, float]] = []
    for part in parts:
        if not isinstance(part, Polygon):
            continue
        coords = list(part.exterior.coords)
        for a, b in zip(coords[:-1], coords[1:]):
            dx = float(b[0] - a[0])
            dy = float(b[1] - a[1])
            length = math.hypot(dx, dy)
            if length < 1.0:
                continue
            normal_azimuth = (math.degrees(math.atan2(dy, -dx)) + 360.0) % 180.0
            edges.append((normal_azimuth, length))
    return edges


def _frontal_index_proxy(building_rows: list[tuple[Any, float]], cell_area: float, wind_dir_deg: float = 0.0) -> float:
    frontal = 0.0
    wind_axis = wind_dir_deg % 180.0
    for row, _area in building_rows:
        height = float(row.get("height_m", 0.0) or 0.0)
        for normal_azimuth, edge_len in _polygon_orientation_weighted_length(row.geometry):
            angle = abs((normal_azimuth - wind_axis + 90.0) % 180.0 - 90.0)
            frontal += edge_len * height * max(0.0, math.cos(math.radians(angle)))
    return frontal / max(cell_area, 1.0)


def _terrain_stats(samples: pd.DataFrame, cell) -> dict[str, float]:
    if samples.empty or not {"x_m", "y_m", "z_m"}.issubset(samples.columns):
        return {
            "terrain_elevation_mean_m": np.nan,
            "terrain_elevation_min_m": np.nan,
            "terrain_elevation_max_m": np.nan,
            "terrain_relief_m": np.nan,
            "terrain_elevation_std_m": np.nan,
            "terrain_slope_proxy": np.nan,
        }
    minx, miny, maxx, maxy = cell.bounds
    sub = samples[
        (samples["x_m"] >= minx)
        & (samples["x_m"] <= maxx)
        & (samples["y_m"] >= miny)
        & (samples["y_m"] <= maxy)
    ]
    if sub.empty:
        return {
            "terrain_elevation_mean_m": np.nan,
            "terrain_elevation_min_m": np.nan,
            "terrain_elevation_max_m": np.nan,
            "terrain_relief_m": np.nan,
            "terrain_elevation_std_m": np.nan,
            "terrain_slope_proxy": np.nan,
        }
    zmin = float(sub["z_m"].min())
    zmax = float(sub["z_m"].max())
    relief = zmax - zmin
    diag = max(math.hypot(maxx - minx, maxy - miny), 1.0)
    return {
        "terrain_elevation_mean_m": float(sub["z_m"].mean()),
        "terrain_elevation_min_m": zmin,
        "terrain_elevation_max_m": zmax,
        "terrain_relief_m": relief,
        "terrain_elevation_std_m": float(sub["z_m"].std(ddof=0)),
        "terrain_slope_proxy": relief / diag,
    }


def extract_morphology_indicators(paths: MorphologyPaths, grid_size_m: float = 250.0) -> dict[str, Any]:
    ensure_output_dirs(paths)
    if not (paths.morphology_dir / "grid_250m_local.geojson").exists():
        prepare_grid(paths, grid_size_m=grid_size_m)
    origin = read_origin(paths.origin_path)
    grid = load_grid_local(paths)
    buildings = _read_layer(paths.buildings_path, origin, "buildings")
    roads = _read_layer(paths.roads_path, origin, "roads")
    green = _read_layer(paths.green_path, origin, "green")
    water = _read_layer(paths.water_path, origin, "water")
    aoi = _read_layer(paths.aoi_path, origin, "aoi")
    aoi_geom = _valid_geoms(aoi).geometry.unary_union if not _valid_geoms(aoi).empty else None
    terrain = pd.read_csv(paths.terrain_samples_path) if paths.terrain_samples_path.exists() else pd.DataFrame()

    rows: list[dict[str, Any]] = []
    for _, cell_row in grid.iterrows():
        grid_cell = cell_row.geometry
        cell = grid_cell.intersection(aoi_geom) if aoi_geom is not None else grid_cell
        if cell.is_empty or cell.area <= 1.0:
            cell = grid_cell
        cell_area = float(cell.area)
        b_rows = _building_rows_in_cell(buildings, cell)
        b_area = sum(area for _, area in b_rows)
        weighted_heights = [float(row.get("height_m", 0.0) or 0.0) * area for row, area in b_rows]
        b_height_mean = sum(weighted_heights) / b_area if b_area else 0.0
        b_height_max = max([float(row.get("height_m", 0.0) or 0.0) for row, _ in b_rows] or [0.0])
        floor_area = sum(float(row.get("height_m", 0.0) or 0.0) / 3.3 * area for row, area in b_rows)
        road_len = _line_length_intersection(roads, cell)
        road_area = 0.0
        for _, r in _valid_geoms(roads).iterrows():
            inter = r.geometry.intersection(cell)
            if not inter.is_empty:
                width = float(r.get("width_m", 6.0) or 6.0)
                road_area += inter.length * width
        green_area = _area_intersection(green, cell)
        water_area = _area_intersection(water, cell)
        tree_area = 0.0
        grass_area = 0.0
        if not green.empty and "kind" in green.columns:
            for _, g in _valid_geoms(green).iterrows():
                inter = g.geometry.intersection(cell)
                if inter.is_empty:
                    continue
                kind = str(g.get("kind", "")).lower()
                if "tree" in kind:
                    tree_area += inter.area
                else:
                    grass_area += inter.area
        else:
            grass_area = green_area
        impervious = min(cell_area, b_area + road_area)
        open_ratio = max(0.0, 1.0 - b_area / max(cell_area, 1.0))
        frontal_n = _frontal_index_proxy(b_rows, cell_area, 0.0)
        frontal_e = _frontal_index_proxy(b_rows, cell_area, 90.0)
        canyon_proxy = b_height_mean / max((road_area / max(road_len, 1.0)), 1.0) if road_len else 0.0
        terrain_stats = _terrain_stats(terrain, cell)
        source_quality = "medium"
        if not paths.terrain_samples_path.exists() or buildings.empty:
            source_quality = "low"
        elif "source" in buildings.columns and buildings["source"].astype(str).str.contains("OpenStreetMap", na=False).any():
            source_quality = "medium_osm_plus_dem"

        row = {
            # Basic information
            "grid_id": cell_row["grid_id"],
            "row": int(cell_row["row"]),
            "col": int(cell_row["col"]),
            "grid_size_m": float(cell_row["grid_size_m"]),
            "area_m2": cell_area,
            "center_lon": float(cell_row["center_lon"]),
            "center_lat": float(cell_row["center_lat"]),
            "data_source_buildings": str(buildings.get("source", pd.Series(["unknown"])).dropna().iloc[0]) if not buildings.empty and "source" in buildings.columns else "missing_or_unknown",
            "data_source_green": str(green.get("source", pd.Series(["unknown"])).dropna().iloc[0]) if not green.empty and "source" in green.columns else "missing_or_unknown",
            "data_source_terrain": "terrain_dem_samples.csv" if paths.terrain_samples_path.exists() else "missing",
            "source_quality_flag": source_quality,
            # Building morphology
            "building_count": len(b_rows),
            "building_footprint_area_m2": b_area,
            "building_coverage_ratio": b_area / max(cell_area, 1.0),
            "building_height_mean_m": b_height_mean,
            "building_height_max_m": b_height_max,
            "building_floor_area_est_m2": floor_area,
            "floor_area_ratio_est": floor_area / max(cell_area, 1.0),
            "building_height_std_m": float(np.std([float(r.get("height_m", 0.0) or 0.0) for r, _ in b_rows])) if b_rows else 0.0,
            # Spatial openness
            "open_space_ratio": open_ratio,
            "road_centerline_length_m": road_len,
            "road_surface_area_est_m2": road_area,
            "impervious_surface_ratio": impervious / max(cell_area, 1.0),
            "unbuilt_pervious_proxy_ratio": max(0.0, 1.0 - impervious / max(cell_area, 1.0)),
            # Ventilation morphology
            "frontal_area_index_north_proxy": frontal_n,
            "frontal_area_index_east_proxy": frontal_e,
            "frontal_area_index_mean_proxy": (frontal_n + frontal_e) * 0.5,
            "height_to_road_width_proxy": canyon_proxy,
            "ventilation_open_corridor_proxy": max(0.0, min(1.0, open_ratio + road_len / max(cell_area, 1.0) * 10.0)),
            # Blue-green space
            "green_area_m2": green_area,
            "green_ratio": green_area / max(cell_area, 1.0),
            "tree_cover_area_m2": tree_area,
            "tree_cover_ratio": tree_area / max(cell_area, 1.0),
            "grass_area_m2": grass_area,
            "grass_ratio": grass_area / max(cell_area, 1.0),
            "water_area_m2": water_area,
            "water_ratio": water_area / max(cell_area, 1.0),
            "blue_green_ratio": min(1.0, (green_area + water_area) / max(cell_area, 1.0)),
            # Terrain
            **terrain_stats,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    csv_path = paths.morphology_dir / "morphology_indicators_250m.csv"
    json_path = paths.morphology_dir / "morphology_indicator_schema.json"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    schema = {
        "status": "success",
        "grid_size_m": grid_size_m,
        "grid_count": len(df),
        "indicator_groups": {
            "basic_information": ["grid_id", "row", "col", "area_m2", "center_lon", "center_lat", "data_source_*", "source_quality_flag"],
            "building_morphology": ["building_count", "building_coverage_ratio", "building_height_*", "floor_area_ratio_est"],
            "spatial_openness": ["open_space_ratio", "road_*", "impervious_surface_ratio", "unbuilt_pervious_proxy_ratio"],
            "ventilation_morphology": ["frontal_area_index_*", "height_to_road_width_proxy", "ventilation_open_corridor_proxy"],
            "blue_green_space": ["green_*", "tree_*", "grass_*", "water_*", "blue_green_ratio"],
            "terrain": ["terrain_elevation_*", "terrain_relief_m", "terrain_slope_proxy"],
        },
        "outputs": {"indicators_csv": str(csv_path)},
    }
    json_path.write_text(json.dumps(schema, ensure_ascii=True, indent=2), encoding="utf-8")
    return schema
