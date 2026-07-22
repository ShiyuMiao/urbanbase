from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MorphologyPaths:
    project_root: Path
    output_root: Path
    gis_dir: Path
    tables_dir: Path
    audit_dir: Path
    morphology_dir: Path
    lcz_dir: Path
    risk_dir: Path
    typical_dir: Path
    figures_dir: Path
    docs_dir: Path
    config_dir: Path

    @property
    def aoi_path(self) -> Path:
        return self.gis_dir / "aoi_boundary.gpkg"

    @property
    def buildings_path(self) -> Path:
        return self.gis_dir / "fused_buildings.gpkg"

    @property
    def roads_path(self) -> Path:
        return self.gis_dir / "fused_roads.gpkg"

    @property
    def green_path(self) -> Path:
        return self.gis_dir / "fused_green.gpkg"

    @property
    def water_path(self) -> Path:
        return self.gis_dir / "fused_water.gpkg"

    @property
    def terrain_samples_path(self) -> Path:
        return self.gis_dir / "terrain_dem_samples.csv"

    @property
    def origin_path(self) -> Path:
        return self.gis_dir / "origin_mapping.json"


def default_paths(project_root: str | Path | None = None, output_root: str | Path | None = None) -> MorphologyPaths:
    root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parents[2]
    out = Path(output_root).resolve() if output_root else root / "outputs_citylbm_voxel_china"
    return MorphologyPaths(
        project_root=root,
        output_root=out,
        gis_dir=out / "02_gis",
        tables_dir=out / "06_tables",
        audit_dir=out / "07_audit",
        morphology_dir=out / "08_morphology",
        lcz_dir=out / "09_lcz",
        risk_dir=out / "14_heat_wind_risk",
        typical_dir=out / "15_typical_blocks",
        figures_dir=out / "10_figures",
        docs_dir=out / "11_docs",
        config_dir=root / "config",
    )


def ensure_output_dirs(paths: MorphologyPaths) -> None:
    for path in [
        paths.audit_dir,
        paths.morphology_dir,
        paths.lcz_dir,
        paths.risk_dir,
        paths.typical_dir,
        paths.figures_dir,
        paths.docs_dir,
        paths.config_dir,
    ]:
        path.mkdir(parents=True, exist_ok=True)
