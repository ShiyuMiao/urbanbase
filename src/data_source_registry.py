from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import csv
import json


@dataclass(frozen=True)
class DataSource:
    name: str
    category: str
    elements: str
    access_method: str
    license: str
    spatial_resolution: str
    update_frequency: str
    api_key_required: bool
    bulk_download_allowed: str
    paper_reproducible: bool
    china_applicability: str
    fallback_to: str
    enabled_by_default: bool
    notes: str


DATA_SOURCES: list[DataSource] = [
    DataSource(
        name="Local curated vector/raster data",
        category="local",
        elements="buildings, roads, water, green, terrain, poi",
        access_method="project data directory",
        license="user supplied; must be documented per dataset",
        spatial_resolution="dataset-specific",
        update_frequency="dataset-specific",
        api_key_required=False,
        bulk_download_allowed="depends on local license",
        paper_reproducible=True,
        china_applicability="high when supplied for the AOI",
        fallback_to="Overture Maps / OpenStreetMap",
        enabled_by_default=True,
        notes="Highest priority when geometry, CRS, license and timestamp are auditable.",
    ),
    DataSource(
        name="Overture Maps buildings / transportation / places",
        category="open-data",
        elements="buildings, roads, poi",
        access_method="download or cloud table export",
        license="CDLA Permissive 2.0 / ODbL depending on theme",
        spatial_resolution="feature-level vector",
        update_frequency="monthly",
        api_key_required=False,
        bulk_download_allowed="yes, subject to Overture terms",
        paper_reproducible=True,
        china_applicability="variable; must check coverage",
        fallback_to="OpenStreetMap",
        enabled_by_default=False,
        notes="Registered but not fetched automatically in this local runner because no project-local Overture extract is present.",
    ),
    DataSource(
        name="OpenStreetMap Overpass",
        category="open-data",
        elements="buildings, roads, water, green, poi",
        access_method="Overpass API with raw JSON cache",
        license="Open Database License 1.0",
        spatial_resolution="volunteer vector mapping; feature-dependent",
        update_frequency="continuous",
        api_key_required=False,
        bulk_download_allowed="limited API use; use extracts for bulk",
        paper_reproducible=True,
        china_applicability="medium to high in mapped Chinese cities",
        fallback_to="deterministic synthetic minimal AOI placeholders",
        enabled_by_default=True,
        notes="Used as the default reproducible online source when no local curated dataset is found.",
    ),
    DataSource(
        name="Geofabrik China / province OSM extract",
        category="open-data",
        elements="buildings, roads, water, green, poi",
        access_method="local .pbf extract if supplied",
        license="Open Database License 1.0",
        spatial_resolution="volunteer vector mapping; feature-dependent",
        update_frequency="daily",
        api_key_required=False,
        bulk_download_allowed="yes, subject to provider fair-use terms",
        paper_reproducible=True,
        china_applicability="medium to high",
        fallback_to="OpenStreetMap Overpass",
        enabled_by_default=False,
        notes="Preferred for large batch jobs, but no local PBF is bundled in this project snapshot.",
    ),
    DataSource(
        name="Copernicus DEM GLO-30 / FABDEM / SRTM family",
        category="terrain",
        elements="terrain",
        access_method="local raster if supplied; procedural fallback otherwise",
        license="source-specific open terms",
        spatial_resolution="about 30 m for common global DEM products",
        update_frequency="static or periodic",
        api_key_required=False,
        bulk_download_allowed="source-specific",
        paper_reproducible=True,
        china_applicability="high at regional scale; not 0.1 m measured precision",
        fallback_to="procedural relief surface with explicit low confidence",
        enabled_by_default=True,
        notes="This runner records 0.1 m voxelization as output-grid resolution, not DEM measurement precision.",
    ),
    DataSource(
        name="ESA WorldCover / Dynamic World / Sentinel-2 classification",
        category="land-cover",
        elements="green, water, impervious, vegetation",
        access_method="local raster if supplied or cloud API outside this offline runner",
        license="source-specific open terms",
        spatial_resolution="10 m nominal for common products",
        update_frequency="annual to near-real-time",
        api_key_required=False,
        bulk_download_allowed="source-specific",
        paper_reproducible=True,
        china_applicability="high for semantic context, limited for 0.1 m geometry",
        fallback_to="OSM green/water tags plus AOI default surface",
        enabled_by_default=False,
        notes="Registered for future raster fusion. Not used unless a project-local raster is supplied.",
    ),
    DataSource(
        name="Tianditu / AMap / Baidu APIs",
        category="commercial-or-national-api",
        elements="roads, poi, imagery, geocoding",
        access_method="API key",
        license="platform terms; must be checked per use",
        spatial_resolution="platform-specific",
        update_frequency="platform-specific",
        api_key_required=True,
        bulk_download_allowed="usually restricted",
        paper_reproducible=False,
        china_applicability="high when licensed",
        fallback_to="OpenStreetMap / local curated data",
        enabled_by_default=False,
        notes="Disabled by default because no legal API key and license record is provided.",
    ),
]


def export_registry(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = [asdict(item) for item in DATA_SOURCES]
    json_path = output_dir / "data_source_registry.json"
    csv_path = output_dir / "data_source_registry.csv"
    json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return {"json": json_path, "csv": csv_path}


def enabled_sources() -> list[dict]:
    return [asdict(item) for item in DATA_SOURCES if item.enabled_by_default]
