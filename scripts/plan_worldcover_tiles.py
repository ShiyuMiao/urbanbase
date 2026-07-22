from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC = PROJECT_ROOT / "src"
SCRIPTS = PROJECT_ROOT / "scripts"
for path in (SRC, SCRIPTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from audit_worldcover_coverage import DEFAULT_SITES as AUDIT_DEFAULT_SITES  # noqa: E402
from audit_worldcover_coverage import AuditSite, parse_site  # noqa: E402
from china_voxel_pipeline import (  # noqa: E402
    RunConfig,
    bbox_lonlat,
    config_output_root,
    discover_esa_worldcover_candidates,
    ensure_dirs,
    expected_esa_worldcover_tiles,
    rel_project_path,
    select_esa_worldcover_raster,
    write_json,
)


TILE_RE = re.compile(r"(N\d{2}|S\d{2})(E\d{3}|W\d{3})", re.IGNORECASE)
ESA_WORLDCOVER_BASE_URL = "https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map"


@dataclass(frozen=True)
class ManifestSite:
    name: str
    lat: float
    lon: float
    half_size_m: float


def parse_manifest_site(value: str, default_half_size_m: float) -> ManifestSite:
    site = parse_site(value)
    return ManifestSite(site.name, site.lat, site.lon, default_half_size_m)


def tile_prefix(tile_name: str) -> str:
    match = TILE_RE.search(tile_name)
    return f"{match.group(1).upper()}{match.group(2).upper()}" if match else ""


def tile_bounds_wgs84(prefix: str) -> dict[str, float] | None:
    match = TILE_RE.fullmatch(prefix)
    if not match:
        return None
    lat_token, lon_token = match.group(1).upper(), match.group(2).upper()
    south = int(lat_token[1:])
    if lat_token.startswith("S"):
        south = -south
    west = int(lon_token[1:])
    if lon_token.startswith("W"):
        west = -west
    return {"west": float(west), "south": float(south), "east": float(west + 3), "north": float(south + 3)}


def tile_download_url(tile_name: str) -> str:
    return f"{ESA_WORLDCOVER_BASE_URL}/{tile_name}"


def remote_content_length(url: str, timeout_s: float = 10.0) -> int | None:
    try:
        request = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            value = response.headers.get("Content-Length")
        return int(value) if value else None
    except Exception:
        curl = "curl.exe" if sys.platform.startswith("win") else "curl"
        completed = subprocess.run(
            [curl, "-L", "-I", "-sS", url],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
        lengths = []
        for line in completed.stdout.splitlines():
            if line.lower().startswith("content-length:"):
                lengths.append(int(line.split(":", 1)[1].strip()))
        return lengths[-1] if lengths else None


def local_file_size(path: str) -> int | None:
    candidate = Path(path)
    return candidate.stat().st_size if candidate.exists() else None


def size_checked_paths(paths: list[str], expected_bytes: int | None) -> tuple[list[str], list[str], str]:
    if expected_bytes is None:
        return paths, [], "unchecked"
    complete: list[str] = []
    incomplete: list[str] = []
    for path in paths:
        size = local_file_size(path)
        if size == expected_bytes:
            complete.append(path)
        else:
            incomplete.append(path)
    return complete, incomplete, "checked"


def site_config(site: ManifestSite, worldcover_path: str, output_root: str) -> RunConfig:
    return RunConfig(
        site_name=f"worldcover_plan_{site.name}",
        site_name_cn=site.name,
        center_lat=site.lat,
        center_lon=site.lon,
        half_size_m=site.half_size_m,
        voxel_size_m=1.0,
        esa_worldcover_path=worldcover_path,
        output_root=output_root,
        strict_real_data=True,
    )


def read_sites_csv(path: Path, default_half_size_m: float) -> list[ManifestSite]:
    sites: list[ManifestSite] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"sites CSV has no header: {path}")
        normalized = {name.strip().lower(): name for name in reader.fieldnames}
        name_key = normalized.get("site_name") or normalized.get("name")
        lat_key = normalized.get("lat") or normalized.get("latitude")
        lon_key = normalized.get("lon") or normalized.get("lng") or normalized.get("longitude")
        half_key = normalized.get("half_size_m") or normalized.get("half_size")
        if not name_key or not lat_key or not lon_key:
            raise ValueError("sites CSV must include site_name/name, lat/latitude, and lon/lng/longitude columns")
        for row in reader:
            name = (row.get(name_key) or "").strip()
            if not name:
                continue
            half_size = default_half_size_m
            if half_key and (row.get(half_key) or "").strip():
                half_size = float(row[half_key])
            sites.append(ManifestSite(name=name, lat=float(row[lat_key]), lon=float(row[lon_key]), half_size_m=half_size))
    return sites


def local_tile_paths_by_name(candidates: list[Path]) -> dict[str, list[str]]:
    paths: dict[str, list[str]] = {}
    for path in candidates:
        paths.setdefault(path.name, []).append(str(path))
    return paths


def flatten_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for site in report["sites"]:
        for tile in site["tiles"]:
            rows.append(
                {
                    "site_name": site["site_name"],
                    "lat": site["lat"],
                    "lon": site["lon"],
                    "half_size_m": site["half_size_m"],
                    "coverage_status": site["coverage_status"],
                    "tile_name": tile["tile_name"],
                    "tile_prefix": tile["tile_prefix"],
                    "tile_status": tile["status"],
                    "tile_bounds_wgs84": json.dumps(tile["tile_bounds_wgs84"], ensure_ascii=True),
                    "local_paths": ";".join(tile["local_paths"]),
                    "selected_path": site.get("selected_path") or "",
                    "bbox_wgs84": json.dumps(site["bbox_wgs84"], ensure_ascii=True),
                    "gee_collection": tile["gee_collection"],
                    "gee_year": tile["gee_year"],
                    "download_url": tile["download_url"],
                    "expected_download_bytes": tile.get("expected_download_bytes") or "",
                    "download_size_status": tile.get("download_size_status") or "",
                    "incomplete_local_paths": ";".join(tile.get("incomplete_local_paths", [])),
                    "suggested_local_filename": tile["suggested_local_filename"],
                }
            )
    return rows


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "site_name",
        "lat",
        "lon",
        "half_size_m",
        "coverage_status",
        "tile_name",
        "tile_prefix",
        "tile_status",
        "tile_bounds_wgs84",
        "local_paths",
        "selected_path",
        "bbox_wgs84",
        "gee_collection",
        "gee_year",
        "download_url",
        "expected_download_bytes",
        "download_size_status",
        "incomplete_local_paths",
        "suggested_local_filename",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def gee_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def gee_rectangle(bounds: dict[str, float]) -> str:
    return f"[{bounds['west']}, {bounds['south']}, {bounds['east']}, {bounds['north']}]"


def build_gee_export_script(missing_tiles: list[str]) -> str:
    lines = [
        "// Auto-generated by scripts/plan_worldcover_tiles.py",
        "// Run in the Google Earth Engine Code Editor, then download the exported GeoTIFFs",
        "// into outputs_citylbm_voxel_china/01_raw using the suggested filenames.",
        "",
        "var worldcover = ee.ImageCollection('ESA/WorldCover/v200')",
        "  .filterDate('2021-01-01', '2022-01-01')",
        "  .first()",
        "  .select('Map');",
        "",
    ]
    if not missing_tiles:
        lines.append("// No missing WorldCover tiles were found in the current manifest.")
        return "\n".join(lines) + "\n"

    for tile_name in missing_tiles:
        prefix = tile_prefix(tile_name)
        bounds = tile_bounds_wgs84(prefix)
        if not bounds:
            continue
        export_name = tile_name.rsplit(".", 1)[0]
        region_name = f"region_{prefix}"
        lines.extend(
            [
                f"var {region_name} = ee.Geometry.Rectangle({gee_rectangle(bounds)}, null, false);",
                "Export.image.toDrive({",
                "  image: worldcover,",
                f"  description: {gee_string(export_name)},",
                "  folder: 'urbanbase_worldcover_tiles',",
                f"  fileNamePrefix: {gee_string(export_name)},",
                f"  region: {region_name},",
                "  scale: 10,",
                "  crs: 'EPSG:4326',",
                "  maxPixels: 1e13",
                "});",
                "",
            ]
        )
    return "\n".join(lines)


def write_gee_export_script(path: Path, missing_tiles: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_gee_export_script(missing_tiles), encoding="utf-8")


def ps_single_quoted(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def build_download_script(missing_tiles: list[str]) -> str:
    lines = [
        "# Auto-generated by scripts/plan_worldcover_tiles.py",
        "# Downloads missing ESA WorldCover GeoTIFFs into outputs_citylbm_voxel_china/01_raw.",
        "$ErrorActionPreference = 'Stop'",
        "$rawDir = Join-Path $PSScriptRoot '..\\01_raw'",
        "New-Item -ItemType Directory -Force -Path $rawDir | Out-Null",
        "",
        "function Get-RemoteLength {",
        "  param([string]$Url)",
        "  $response = Invoke-WebRequest -UseBasicParsing -Method Head -Uri $Url",
        "  $length = $response.Headers['Content-Length']",
        "  if ($length -is [array]) { $length = $length[0] }",
        "  return [int64]$length",
        "}",
        "",
        "function Get-LocalLength {",
        "  param([string]$Path)",
        "  if (Test-Path -LiteralPath $Path) { return [int64](Get-Item -LiteralPath $Path).Length }",
        "  return [int64]0",
        "}",
        "",
    ]
    if not missing_tiles:
        lines.append("Write-Host 'No missing WorldCover tiles were found in the current manifest.'")
        return "\n".join(lines) + "\n"
    for tile_name in missing_tiles:
        lines.extend(
            [
                f"$url = {ps_single_quoted(tile_download_url(tile_name))}",
                f"$out = Join-Path $rawDir {ps_single_quoted(tile_name)}",
                "$part = \"$out.part\"",
                "$expectedLength = Get-RemoteLength $url",
                "$outLength = Get-LocalLength $out",
                "if ($outLength -eq $expectedLength) {",
                f"  Write-Host {ps_single_quoted('Already complete: ' + tile_name)}",
                "} else {",
                "  if ($outLength -gt 0) {",
                "    Move-Item -LiteralPath $out -Destination $part -Force",
                "  } elseif (Test-Path -LiteralPath $out) {",
                "    Move-Item -LiteralPath $out -Destination $part -Force",
                "  }",
                f"  Write-Host {ps_single_quoted('Downloading/resuming: ' + tile_name)}",
                "  if (Test-Path -LiteralPath $part) {",
                "    curl.exe -L -C - $url -o $part",
                "  } else {",
                "    curl.exe -L $url -o $part",
                "  }",
                "  if ($LASTEXITCODE -ne 0) { throw \"curl failed for $url\" }",
                "  $partLength = Get-LocalLength $part",
                "  if ($partLength -ne $expectedLength) {",
                "    throw \"Incomplete download for $out; expected $expectedLength bytes, got $partLength bytes\"",
                "  }",
                "  Move-Item -LiteralPath $part -Destination $out -Force",
                "}",
                "",
            ]
        )
    return "\n".join(lines)


def write_download_script(path: Path, missing_tiles: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_download_script(missing_tiles), encoding="utf-8")


def plan_worldcover_tiles(
    sites: list[ManifestSite],
    worldcover_path: str,
    output_root: str,
    remote_size_lookup: Callable[[str], int | None] | None = None,
) -> dict[str, Any]:
    base_config = RunConfig(
        site_name="worldcover_tile_manifest",
        site_name_cn="worldcover_tile_manifest",
        output_root=output_root,
        esa_worldcover_path=worldcover_path,
    )
    dirs = ensure_dirs(base_config)
    candidates = discover_esa_worldcover_candidates(base_config, dirs)
    candidate_paths_by_name = local_tile_paths_by_name(candidates)
    size_lookup = remote_size_lookup or (lambda tile_name: remote_content_length(tile_download_url(tile_name)))
    expected_bytes_by_name: dict[str, int | None] = {}

    site_reports: list[dict[str, Any]] = []
    missing_expected_tiles: set[str] = set()
    covered_count = 0
    for site in sites:
        config = site_config(site, worldcover_path, output_root)
        selection = select_esa_worldcover_raster(config, dirs)
        expected_tiles = expected_esa_worldcover_tiles(config)
        selected_path = selection.get("selected_path")

        tile_records: list[dict[str, Any]] = []
        for tile_name in expected_tiles:
            prefix = tile_prefix(tile_name)
            paths = candidate_paths_by_name.get(tile_name, [])
            try:
                if tile_name not in expected_bytes_by_name:
                    expected_bytes_by_name[tile_name] = size_lookup(tile_name)
                expected_bytes = expected_bytes_by_name[tile_name]
                size_warning = None
            except Exception as exc:
                expected_bytes = None
                expected_bytes_by_name[tile_name] = None
                size_warning = f"remote_size_unchecked: {exc}"
            complete_paths, incomplete_paths, size_status = size_checked_paths(paths, expected_bytes)
            selected_is_complete = selected_path and any(Path(path) == Path(selected_path) for path in complete_paths)
            if selected_is_complete:
                tile_status = "selected_local"
            elif complete_paths:
                tile_status = "present_but_not_selected"
            elif incomplete_paths:
                tile_status = "present_incomplete_or_wrong_size"
                missing_expected_tiles.add(tile_name)
            else:
                tile_status = "missing"
                missing_expected_tiles.add(tile_name)
            tile_records.append(
                {
                    "tile_name": tile_name,
                    "tile_prefix": prefix,
                    "tile_bounds_wgs84": tile_bounds_wgs84(prefix),
                    "status": tile_status,
                    "local_paths": paths,
                    "complete_local_paths": complete_paths,
                    "incomplete_local_paths": incomplete_paths,
                    "suggested_local_filename": tile_name,
                    "download_url": tile_download_url(tile_name),
                    "expected_download_bytes": expected_bytes,
                    "download_size_status": size_status,
                    "download_size_warning": size_warning,
                    "gee_collection": "ESA/WorldCover/v200",
                    "gee_year": 2021,
                }
            )

        has_complete_expected_tiles = bool(tile_records) and all(
            tile["status"] in {"selected_local", "present_but_not_selected"} for tile in tile_records
        )
        coverage_status = (
            "covered"
            if selection.get("selection_status") == "selected_intersecting_raster" and has_complete_expected_tiles
            else "missing_coverage"
        )
        if coverage_status == "covered":
            covered_count += 1

        site_reports.append(
            {
                "site_name": site.name,
                "lat": site.lat,
                "lon": site.lon,
                "half_size_m": site.half_size_m,
                "bbox_wgs84": bbox_lonlat(config),
                "coverage_status": coverage_status,
                "selection_status": selection.get("selection_status"),
                "selected_path": selected_path,
                "selected_relative_path": rel_project_path(Path(selected_path)) if selected_path else None,
                "expected_tiles": expected_tiles,
                "tiles": tile_records,
            }
        )

    output_json = dirs["logs"] / "worldcover_tile_request_manifest.json"
    output_csv = dirs["logs"] / "worldcover_tile_request_manifest.csv"
    output_gee_js = dirs["logs"] / "worldcover_gee_export_tasks.js"
    output_download_ps1 = dirs["logs"] / "worldcover_download_missing_tiles.ps1"
    missing_site_count = len(site_reports) - covered_count
    missing_tiles_sorted = sorted(missing_expected_tiles)
    report = {
        "status": "success" if missing_site_count == 0 else "completed_with_missing_tiles",
        "output_root": str(config_output_root(base_config)),
        "output_json": str(output_json),
        "output_csv": str(output_csv),
        "output_gee_js": str(output_gee_js),
        "output_download_ps1": str(output_download_ps1),
        "site_count": len(site_reports),
        "covered_site_count": covered_count,
        "missing_site_count": missing_site_count,
        "candidate_count": len(candidates),
        "missing_tile_count": len(missing_expected_tiles),
        "missing_expected_tiles": missing_tiles_sorted,
        "sites": site_reports,
        "candidate_files": [
            {
                "name": path.name,
                "path": str(path),
                "relative_path": rel_project_path(path),
            }
            for path in candidates
        ],
        "notes": [
            "Use this manifest before formal real-data modeling runs.",
            "A site is covered only when a readable local WorldCover raster intersects the AOI.",
            "Missing tiles must be exported/downloaded as real ESA WorldCover GeoTIFFs before strict formal runs.",
            "The generated GEE script exports only missing tiles and preserves the expected ESA WorldCover filenames.",
            "The generated PowerShell script downloads missing tiles from the official ESA WorldCover S3 bucket.",
            "Local tiles with a known official Content-Length mismatch are treated as missing coverage.",
        ],
    }
    write_json(output_json, report)
    write_csv(output_csv, flatten_rows(report))
    write_gee_export_script(output_gee_js, missing_tiles_sorted)
    write_download_script(output_download_ps1, missing_tiles_sorted)
    return report


def default_sites(default_half_size_m: float) -> list[ManifestSite]:
    return [ManifestSite(site.name, site.lat, site.lon, default_half_size_m) for site in AUDIT_DEFAULT_SITES]


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a WorldCover tile request manifest for planned VoxCity sites.")
    parser.add_argument("--site", action="append", help="Site as name,lat,lon. Can be repeated.")
    parser.add_argument("--sites-csv", type=Path, help="Optional CSV with site_name/name, lat, lon, and optional half_size_m.")
    parser.add_argument("--half-size-m", type=float, default=250.0, help="Default AOI half size for --site/default sites.")
    parser.add_argument("--worldcover-path", default="", help="Explicit WorldCover GeoTIFF path to include in candidate search.")
    parser.add_argument("--output-root", default="", help="Pipeline output root for the manifest JSON/CSV.")
    args = parser.parse_args()

    sites: list[ManifestSite] = []
    if args.sites_csv:
        sites.extend(read_sites_csv(args.sites_csv, args.half_size_m))
    if args.site:
        sites.extend(parse_manifest_site(value, args.half_size_m) for value in args.site)
    if not sites:
        sites = default_sites(args.half_size_m)

    result = plan_worldcover_tiles(sites, args.worldcover_path, args.output_root)
    print(json.dumps(result, ensure_ascii=True, indent=2))
    raise SystemExit(0)


if __name__ == "__main__":
    main()
