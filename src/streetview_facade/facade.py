from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from .coordinates import FacadePlane, LocalOrigin, compass_azimuth_from_vector, local_xy

try:
    import geopandas as gpd
    from shapely.geometry import Polygon, MultiPolygon
    from shapely.geometry.polygon import orient
    from shapely.ops import transform
except Exception:  # pragma: no cover - optional geospatial stack is validated at runtime.
    gpd = None
    Polygon = None
    MultiPolygon = None
    orient = None
    transform = None


def _polygon_to_local(poly, origin: LocalOrigin):
    def _xy(lon: float, lat: float, z: float | None = None):
        x, y = local_xy(lon, lat, origin)
        return (x, y) if z is None else (x, y, z)

    return transform(_xy, poly)


def polygon_facades(poly, building_id: str, min_length_m: float = 2.0) -> list[FacadePlane]:
    if Polygon is None:
        raise ImportError("shapely is required to extract facade planes")
    poly = orient(poly, sign=1.0)
    coords = list(poly.exterior.coords)
    facades: list[FacadePlane] = []
    for idx, (a, b) in enumerate(zip(coords[:-1], coords[1:])):
        x0, y0 = float(a[0]), float(a[1])
        x1, y1 = float(b[0]), float(b[1])
        dx, dy = x1 - x0, y1 - y0
        length = (dx * dx + dy * dy) ** 0.5
        if length < min_length_m:
            continue
        nx, ny = dy / length, -dx / length
        azimuth = compass_azimuth_from_vector(nx, ny)
        facades.append(
            FacadePlane(
                building_id=str(building_id),
                facade_id=f"{building_id}_facade_{idx:03d}",
                x0=round(x0, 3),
                y0=round(y0, 3),
                x1=round(x1, 3),
                y1=round(y1, 3),
                nx=round(nx, 6),
                ny=round(ny, 6),
                length_m=round(length, 3),
                azimuth_deg=round(azimuth, 3),
            )
        )
    return facades


def extract_facades_from_buildings(
    building_path: str | Path,
    origin: LocalOrigin,
    id_column: str | None = None,
    min_length_m: float = 2.0,
) -> list[FacadePlane]:
    if gpd is None:
        raise ImportError("geopandas is required to load building footprints")
    gdf = gpd.read_file(building_path)
    if gdf.empty:
        return []

    epsg = gdf.crs.to_epsg() if gdf.crs is not None else None
    facades: list[FacadePlane] = []
    for idx, row in gdf.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        building_id = str(row.get(id_column, idx)) if id_column else str(row.get("osm_id", idx))
        parts = list(geom.geoms) if MultiPolygon is not None and isinstance(geom, MultiPolygon) else [geom]
        for part_no, poly in enumerate(parts):
            if not isinstance(poly, Polygon):
                continue
            local_poly = _polygon_to_local(poly, origin) if epsg == 4326 else poly
            facades.extend(polygon_facades(local_poly, f"{building_id}_{part_no}", min_length_m=min_length_m))
    return facades


def write_facade_csv(facades: Iterable[FacadePlane], path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [facade.to_row() for facade in facades]
    fieldnames = list(rows[0].keys()) if rows else [
        "building_id", "facade_id", "x0", "y0", "x1", "y1", "nx", "ny", "length_m", "azimuth_deg"
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path
