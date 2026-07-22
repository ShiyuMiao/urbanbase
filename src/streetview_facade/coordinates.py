from __future__ import annotations

import math
from dataclasses import asdict, dataclass

EARTH_RADIUS_M = 6_378_137.0


@dataclass(frozen=True)
class LocalOrigin:
    lon: float
    lat: float
    elevation_m: float = 0.0
    crs: str = "local_tangent_meters"


@dataclass(frozen=True)
class FacadePlane:
    building_id: str
    facade_id: str
    x0: float
    y0: float
    x1: float
    y1: float
    nx: float
    ny: float
    length_m: float
    azimuth_deg: float

    @property
    def centroid_xy(self) -> tuple[float, float]:
        return ((self.x0 + self.x1) * 0.5, (self.y0 + self.y1) * 0.5)

    def to_row(self) -> dict[str, float | str]:
        return asdict(self)


def local_xy(lon: float, lat: float, origin: LocalOrigin) -> tuple[float, float]:
    x = math.radians(lon - origin.lon) * EARTH_RADIUS_M * math.cos(math.radians(origin.lat))
    y = math.radians(lat - origin.lat) * EARTH_RADIUS_M
    return x, y


def lonlat_from_xy(x: float, y: float, origin: LocalOrigin) -> tuple[float, float]:
    lon = origin.lon + math.degrees(x / (EARTH_RADIUS_M * math.cos(math.radians(origin.lat))))
    lat = origin.lat + math.degrees(y / EARTH_RADIUS_M)
    return lon, lat


def compass_azimuth_from_vector(dx: float, dy: float) -> float:
    return (math.degrees(math.atan2(dx, dy)) + 360.0) % 360.0


def heading_unit_vector(heading_deg: float) -> tuple[float, float]:
    radians = math.radians(heading_deg)
    return math.sin(radians), math.cos(radians)


def angular_difference_deg(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def distance_xy(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def bearing_between_xy(src: tuple[float, float], dst: tuple[float, float]) -> float:
    return compass_azimuth_from_vector(dst[0] - src[0], dst[1] - src[1])
