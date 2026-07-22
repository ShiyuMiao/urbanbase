from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import json
from shapely.ops import transform

EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class LocalOrigin:
    lon: float
    lat: float
    elevation_m: float = 0.0


def read_origin(path: str | Path) -> LocalOrigin:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return LocalOrigin(
        lon=float(data["origin_lon"]),
        lat=float(data["origin_lat"]),
        elevation_m=float(data.get("origin_elevation", 0.0)),
    )


def local_xy(lon: float, lat: float, origin: LocalOrigin) -> tuple[float, float]:
    x = math.radians(lon - origin.lon) * EARTH_RADIUS_M * math.cos(math.radians(origin.lat))
    y = math.radians(lat - origin.lat) * EARTH_RADIUS_M
    return x, y


def lonlat_from_xy(x: float, y: float, origin: LocalOrigin) -> tuple[float, float]:
    lon = origin.lon + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin.lat))))
    lat = origin.lat + math.degrees(y / EARTH_RADIUS_M)
    return lon, lat


def geometry_to_local(geom: Any, origin: LocalOrigin):
    def _xy(lon: float, lat: float, z: float | None = None):
        x, y = local_xy(lon, lat, origin)
        return (x, y) if z is None else (x, y, z)

    return transform(_xy, geom)


def geometry_to_lonlat(geom: Any, origin: LocalOrigin):
    def _lonlat(x: float, y: float, z: float | None = None):
        lon, lat = lonlat_from_xy(x, y, origin)
        return (lon, lat) if z is None else (lon, lat, z)

    return transform(_lonlat, geom)
