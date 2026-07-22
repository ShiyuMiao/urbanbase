from __future__ import annotations

import json
import math
import warnings
from pathlib import Path
from typing import Any

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from .coordinates import geometry_to_local, geometry_to_lonlat, lonlat_from_xy, read_origin
from .paths import MorphologyPaths, ensure_output_dirs


def _load_aoi_local(paths: MorphologyPaths):
    origin = read_origin(paths.origin_path)
    aoi = gpd.read_file(paths.aoi_path)
    if aoi.empty:
        raise ValueError(f"AOI layer is empty: {paths.aoi_path}")
    if aoi.crs is None or aoi.crs.to_epsg() != 4326:
        raise ValueError(f"AOI must be EPSG:4326 for this phase, got {aoi.crs}")
    return geometry_to_local(aoi.geometry.unary_union, origin), origin


def prepare_grid(paths: MorphologyPaths, grid_size_m: float = 250.0, buffer_m: float = 0.0) -> dict[str, Any]:
    ensure_output_dirs(paths)
    aoi_local, origin = _load_aoi_local(paths)
    minx, miny, maxx, maxy = aoi_local.bounds
    minx = math.floor((minx - buffer_m) / grid_size_m) * grid_size_m
    miny = math.floor((miny - buffer_m) / grid_size_m) * grid_size_m
    maxx = math.ceil((maxx + buffer_m) / grid_size_m) * grid_size_m
    maxy = math.ceil((maxy + buffer_m) / grid_size_m) * grid_size_m

    rows: list[dict[str, Any]] = []
    local_geoms = []
    lonlat_geoms = []
    row_idx = 0
    y = miny
    while y < maxy - 1e-9:
        col_idx = 0
        x = minx
        while x < maxx - 1e-9:
            cell = box(x, y, x + grid_size_m, y + grid_size_m)
            clipped = cell.intersection(aoi_local)
            if not clipped.is_empty and clipped.area > 1.0:
                grid_id = f"grid_{row_idx:03d}_{col_idx:03d}"
                cx = x + grid_size_m * 0.5
                cy = y + grid_size_m * 0.5
                center_lon, center_lat = lonlat_from_xy(cx, cy, origin)
                rows.append(
                    {
                        "grid_id": grid_id,
                        "row": row_idx,
                        "col": col_idx,
                        "grid_size_m": grid_size_m,
                        "cell_area_m2": round(cell.area, 3),
                        "aoi_intersection_area_m2": round(clipped.area, 3),
                        "center_x_m": round(cx, 3),
                        "center_y_m": round(cy, 3),
                        "center_lon": center_lon,
                        "center_lat": center_lat,
                    }
                )
                local_geoms.append(cell)
                lonlat_geoms.append(geometry_to_lonlat(cell, origin))
            x += grid_size_m
            col_idx += 1
        y += grid_size_m
        row_idx += 1

    grid_local = gpd.GeoDataFrame(rows, geometry=local_geoms)
    grid_lonlat = gpd.GeoDataFrame(rows, geometry=lonlat_geoms, crs="EPSG:4326")
    local_path = paths.morphology_dir / "grid_250m_local.geojson"
    lonlat_path = paths.morphology_dir / "grid_250m_wgs84.geojson"
    csv_path = paths.morphology_dir / "grid_250m_index.csv"
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="'crs' was not provided.*")
        grid_local.to_file(local_path, driver="GeoJSON")
    grid_lonlat.to_file(lonlat_path, driver="GeoJSON")
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    summary = {
        "status": "success",
        "grid_size_m": grid_size_m,
        "buffer_m": buffer_m,
        "grid_count": len(rows),
        "outputs": {
            "grid_local": str(local_path),
            "grid_wgs84": str(lonlat_path),
            "grid_index": str(csv_path),
        },
    }
    (paths.morphology_dir / "grid_prepare_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    return summary


def load_grid_local(paths: MorphologyPaths) -> gpd.GeoDataFrame:
    path = paths.morphology_dir / "grid_250m_local.geojson"
    if not path.exists():
        prepare_grid(paths)
    return gpd.read_file(path)
